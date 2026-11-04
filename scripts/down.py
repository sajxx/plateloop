"""Stop the detector endpoint (the model and config stay, so up.py restores service)."""
from _common import ENDPOINT, SM

try:
    SM.delete_endpoint(EndpointName=ENDPOINT)
    print("deleting", ENDPOINT)
except SM.exceptions.ClientError as e:
    print("nothing to delete:", e.response["Error"]["Message"])
