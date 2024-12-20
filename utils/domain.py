from .http_utils import send_request, send_files
import json
import re
import base64
from PIL import Image
import io
import yaml

class Domain:
    def __init__(self, domain_config):
        """
        Initialize the Domain object.
        
        :param domain_config: dict type that contains domain configurations.
        """
        self.domain_id = domain_config["domain_id"]
        self.account = domain_config["posemesh_account"]
        self.password = domain_config["posemesh_password"]
        self.map_endpoint = domain_config["map_endpoint"]
        
        self._posemesh_token = ''
        self._dds_token = ''
        self._domain_info = {}
        self._domain_server = None

    def auth(self):
        # Auth User Posemesh
        url1 = "https://api.posemesh.org/user/login"
        headers1 = {'Content-Type': 'application/json',
                    'Accept': 'application/json'}
        body1 = {'email': self.account,
                 'password': self.password}
        
        ret1, response1 = send_request('POST', url1, headers1, body1)
        if not ret1:
            return False, 'Failed to authenticate posemesh account'
        rep_json1 = json.loads(response1.text)
        self._posemesh_token = rep_json1['access_token']

        # Auth DDS
        url2 = "https://api.posemesh.org/service/domains-access-token"
        headers2 = {'Accept': 'application/json',
                    'Authorization': f"Bearer {self._posemesh_token}"}
        ret2, response2 = send_request('POST', url2, headers2)
        if not ret2:
            return False, 'Failed to authenticate domain dds'
        rep_json2 = json.loads(response2.text)
        self._dds_token = rep_json2['access_token']

        # Auth Domain
        url3 = f"https://dds.posemesh.org/api/v1/domains/{self.domain_id}/auth"
        headers3 = {'Accept': 'application/json',
                    'Authorization': f"Bearer {self._dds_token}"}
        ret3, response3 = send_request('POST', url3, headers3)
        if not ret3:
            return False, 'Failed to authenticate domain access'
        self._domain_info = json.loads(response3.text)
        self._domain_server = self._domain_info["domain_server"]["url"]

        return True, ''

    def get_map(self, image_format="png", resolution=20):
        method = 'POST'

        url = self.map_endpoint
        headers = {'authorization': f'Bearer {self._domain_info["access_token"]}'}

        body = {
            'domainId': self.domain_id,
            'domainServerUrl': self._domain_server,
            'height': 0.1,
            'pixelsPerMeter': resolution
        }

        success, response = send_request(method, url, headers, body)

        raw_data = response.text

        # Split the data using the boundary marker
        boundary = raw_data.split("\n", 1)[0].strip()
        parts = raw_data.split(boundary)

        # Initialize placeholders for the image and YAML data
        image_data = None
        yaml_data = None

        # Iterate through each part of the form-data
        for part in parts:
            if "name=\"png\"" in part:
                # Extract and decode the base64 image data, handle newlines
                image_data_match = re.search(r"name=\"png\"\s*\n([a-zA-Z0-9+/=\n]+)", part)
                if image_data_match:
                    # Remove any newlines or spaces in the base64-encoded data
                    encoded_image = "".join(image_data_match.group(1).splitlines())
                    image_data = base64.b64decode(encoded_image)
            elif "name=\"yaml\"" in part:
                # Extract the YAML content
                yaml_data_match = re.search(r"name=\"yaml\"\s*\n(.+)", part, re.DOTALL)
                if yaml_data_match:
                    yaml_data = yaml_data_match.group(1).strip()

        # Save the image data in the specified format
        image_filename = f"map.{image_format}"  # Determine the file name dynamically
        if image_data:
            try:
                image = Image.open(io.BytesIO(image_data))
                if image_format == "png":
                    image.save(image_filename, "PNG")
                elif image_format == "bmp":
                    image.convert("RGB").save(image_filename, "BMP")  # Ensure RGB for 24-bit BMP
                elif image_format == "pgm":
                    image = image.convert("L")  # Convert to grayscale
                    width, height = image.size

                    # Create a binary occupancy grid: 0 (free/black), 255 (occupied/white), 128 (unknown/gray)
                    binary_grid = []
                    for pixel in image.getdata():
                        if pixel > 165:  # Occupied threshold (65% of 255)
                            binary_grid.append(255)  # Occupied (white)
                        elif pixel < 50:  # Free threshold (19.6% of 255)
                            binary_grid.append(0)  # Free (black)
                        else:
                            binary_grid.append(128)  # Unknown (gray)

                    # Save the binary occupancy grid as a PGM file
                    with open(image_filename, "w") as pgm_file:
                        pgm_file.write(f"P2\n{width} {height}\n255\n")
                        pgm_file.write("\n".join(
                            " ".join(map(str, binary_grid[i:i + width])) for i in range(0, len(binary_grid), width)))

                print(f"Image saved as {image_filename}")
            except Exception as e:
                print(f"Failed to save image in {image_format} format: {e}")
        else:
            print("Image data not found or could not be saved.")

        # Update the YAML file to reference the correct image file
        if yaml_data:
            try:
                yaml_dict = yaml.safe_load(yaml_data)
                yaml_dict['image'] = image_filename  # Update the image field
                with open("map.yaml", "w") as yaml_file:
                    yaml.dump(yaml_dict, yaml_file)
                print("Updated YAML saved as map.yaml")
            except Exception as e:
                print(f"Failed to save updated YAML: {e}")
        else:
            print("YAML data not found or could not be saved.")


