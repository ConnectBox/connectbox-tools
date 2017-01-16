#!/usr/bin/python
import urllib2
import yaml
import json
import argparse

from ansible.module_utils.basic import *

def generate_icon_metadata(tag, var_name):
    response = urllib2.urlopen("https://raw.githubusercontent.com/FortAwesome/Font-Awesome/%s/src/icons.yml" % tag)
    source = response.read()
    result = yaml.load(source)

    id_list = []
    name_dict = dict()
    for icon in result['icons']:
        id_list.append(icon['id'])
        name_dict[icon['name']] = icon['id']

    icon_metadata = dict()
    icon_metadata['ids'] = id_list
    icon_metadata['names'] = name_dict

    print("var %s = %s;" % (var_name, json.dumps(icon_metadata)))

def main(args):
    generate_icon_metadata(args['tag'], args['variable'])

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Salesforce integration for Beartalk.')
    parser.add_argument('-t','--tag', type=str,
        help='Font Awesome tag', default='v4.7.0', required=False)
    parser.add_argument('-v','--variable', type=str,
        help='Javascript variable name for metadata', default='iconMetadata', required=False)

    main(vars(parser.parse_args()))