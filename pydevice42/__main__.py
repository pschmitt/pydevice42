import argparse

parser = argparse.ArgumentParser()
parser.add_argument("-u", "--user", help="Device 42 username")
parser.add_argument("-p", "--password", help="Device 42 password")
parser.add_argument(
    "-w", "--host", help="Device 42 host. ie: https://www.(etc)"
)

args = parser.parse_args()
# Do whatever it is you want here
