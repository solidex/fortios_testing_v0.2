import re
from FGParser import *

from argparse import ArgumentParser

parser = ArgumentParser()
parser.add_argument("-f", "--file", dest="filename", required=True,
                    help="input config file", metavar="FILE")

parser.add_argument("-o", "--output-dir", dest="output_dir", required=True,
                    help="output dir", metavar="FILE")

args = parser.parse_args()


filename = args.filename
output_dir = args.output_dir

parser = FGParser(filename)


parser.dump_state_data(block_name="firewall policy", output_dir=output_dir)
parser.dump_state_data(block_name="firewall address", output_dir=output_dir)
parser.dump_state_data(block_name="firewall service custom", output_dir=output_dir)
