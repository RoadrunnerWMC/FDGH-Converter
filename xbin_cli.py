#!/usr/bin/python3
# xbin_cli.py from FDGH Converter 4.0
# Copyright (C) 2017-2022 RoadrunnerWMC

# FDGH Converter is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# FDGH Converter is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with FDGH Converter.  If not, see <http://www.gnu.org/licenses/>.


import argparse
from pathlib import Path

from typing import List

import fdgh_converter


def handle_unpack(args: argparse.Namespace) -> None:
    """
    Handle the "unpack" command
    """
    print('Extracting XBIN...')

    xbin_data = args.input_file.read_bytes()
    endianness, out_data, metadata, version = fdgh_converter.load_xbin(xbin_data)

    endianness_word = 'big' if endianness == '>' else 'little'
    print(f'Configuration string for this XBIN: {version},{endianness_word},{metadata:#x}')

    fdgh_converter.get_output_path(args, '.unpacked.bin').write_bytes(out_data)


def handle_pack(args: argparse.Namespace) -> None:
    """
    Handle the "pack" command
    """
    if args.config.count(',') != 2:
        raise ValueError('"config" must be a comma-separated triple with three parts')

    version_str, endianness_str, metadata_str = args.config.split(',')

    if version_str not in '24':
        raise ValueError('XBIN version must be 2 or 4')
    version = int(version_str)

    endianness_word = endianness_str.lower()
    if endianness_word not in {'big', 'little'}:
        raise ValueError('endianness must be "big" or "little"')
    endianness = '<' if endianness_word.lower() == 'little' else '>'

    try:
        metadata = int(metadata_str, 0)
    except ValueError:
        raise ValueError('XBIN metadata must be an integer')

    print('Packing XBIN...')

    embedded_data = args.input_file.read_bytes()
    xbin_data = fdgh_converter.save_xbin(endianness, embedded_data, metadata, version)
    fdgh_converter.get_output_path(args, '.packed.bin').write_bytes(xbin_data)


def main(argv:List[str]=None) -> None:
    """
    Main method run automatically when this module is invoked as a
    script
    """
    parser = argparse.ArgumentParser(
        description='FDGH Converter XBIN CLI: pack and unpack XBIN files from the command line.')
    subparsers = parser.add_subparsers(title='commands',
        description='(run a command with -h for additional help)')

    parser_unpack = subparsers.add_parser('unpack', aliases=['extract'],
        help='unpack a file from an XBIN container')
    parser_unpack.add_argument('input_file', type=Path,
        help='input XBIN file to unpack')
    parser_unpack.add_argument('output_file', nargs='?', type=Path,
        help='what to save the embedded file as')
    parser_unpack.add_argument('--overwrite', action='store_true',
        help="overwrite the output file if it already exists (only needed if an output filename isn't explicitly specified)")
    parser_unpack.set_defaults(func=handle_unpack)

    parser_pack = subparsers.add_parser('pack',
        help='pack a file into an XBIN container')
    parser_pack.add_argument('input_file', type=Path,
        help='input file to pack')
    parser_pack.add_argument('config',
        help='required XBIN configuration info as a comma-separated triple (no spaces): "version,endianness,metadata".'
        ' For example, KRtDL\'s FDGH file is "2,big,0xfde9", and KatFL\'s is "4,little,0xfde9".'
        ' The correct config string for an XBIN is printed when unpacking it with the "unpack" command.')
    parser_pack.add_argument('output_file', nargs='?', type=Path,
        help='what to save the XBIN file as')
    parser_pack.add_argument('--overwrite', action='store_true',
        help="overwrite the output file if it already exists (only needed if an output filename isn't explicitly specified)")
    parser_pack.set_defaults(func=handle_pack)

    # Parse args and run appropriate function
    args = parser.parse_args(argv)
    if hasattr(args, 'func'):
        args.func(args)
    else:  # this happens if no arguments were specified at all
        parser.print_usage()


if __name__ == '__main__':
    main()
