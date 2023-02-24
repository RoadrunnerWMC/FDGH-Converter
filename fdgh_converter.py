#!/usr/bin/python3
# FDGH Converter 4.0
# A script that converts FDGH files (found in several Kirby games) to and
# from XML.
# Copyright (C) 2016-2022 RoadrunnerWMC

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
import datetime
from pathlib import Path
import struct
from typing import Any, List, Literal, Optional
from xml.etree import ElementTree as etree


Endianness = Literal['<', '>']


DEFAULT_WORLDMAP_UNKNOWN_VALUE = 2
XBIN_MAGIC =  b'XBIN'
XBIN_MAGIC_BE = XBIN_MAGIC + b'\x12\x34'
XBIN_MAGIC_LE = XBIN_MAGIC + b'\x34\x12'
FDGH_MAGIC_BE = b'FDGH'
FDGH_MAGIC_LE = b'HGDF'

XML_COMMENT = 'This XML file was generated on {} by FDGH Converter 4.0 (https://github.com/RoadrunnerWMC/FDGH-Converter)'


# These make the code cleaner!
def unpack_u32(end: Endianness, *args) -> Any:
    return struct.unpack(end + 'I', *args)[0]
def unpack_u32_from(end: Endianness, *args) -> Any:
    return struct.unpack_from(end + 'I', *args)[0]
def pack_u32(end: Endianness, *args) -> Any:
    return struct.pack(end + 'I', *args)
def pack_u64(end: Endianness, *args) -> Any:
    return struct.pack(end + 'Q', *args)


def load_4b_length_prefixed_string(end: Endianness, data: bytes) -> str:
    """
    Load a 4-byte length prefixed string.
    """
    strLen = unpack_u32(end, data[:4])
    return data[4:4+strLen].decode('latin-1')


def pack_4b_length_prefixed_padded_string(end: Endianness, string: str, num_null_terminators:int=4) -> bytes:
    """
    Pack a 4-byte length prefixed string.
    Most games add 4 null-terminator bytes to the end of each string,
    before aligning to multiples of 4 (so, 4-7 bytes of padding total).
    This was finally fixed in Kirby and the Forgotten Land, which now
    adds just one null terminator before aligning to 4.
    """
    encoded = pack_u32(end, len(string))
    encoded += string.encode('latin-1')
    encoded += b'\0' * num_null_terminators
    while len(encoded) % 4:
        encoded += b'\0'
    return encoded


def fnv1a_64(data: bytes) -> int:
    """
    Calculate the 64-bit FNV-1a hash of a bytes object:
    https://en.wikipedia.org/wiki/Fowler%E2%80%93Noll%E2%80%93Vo_hash_function
    """
    hash = 0xcbf29ce484222325
    for b in data:
        hash = ((hash ^ b) * 0x100000001b3) & 0xffffffffffffffff
    return hash


def load_string_list(end: Endianness, data: bytes, offset_to_data: int) -> (List[str], Optional[Literal['fnv1a_64']]):
    """
    Load a string list. This consists of a 4-byte string count (call it
    "n"), followed by n offsets, followed by the data region the offsets
    point to. Each offset points to a 4-byte length-prefixed string.

    The offset_to_data parameter is the absolute offset of the data
    being passed. This is needed in order to convert the absolute
    offsets of the string-offsets section into relative offsets, which
    can be loaded correctly.

    The return value is the string list, and a string indicating the
    type of hash detected to be in use ('fnv1a_64' for Kirby and the
    Forgotten Land, None for all previous games).
    """
    number_of_strings = unpack_u32(end, data[:4])

    uses_hashes = (data[4:8] == b'\0\0\0\0')

    strs = []
    for i in range(number_of_strings):
        if uses_hashes:
            str_off = unpack_u32_from(end, data, 16 + 16 * i)
        else:
            str_off = unpack_u32_from(end, data, 4 + 4 * i)
        str_off -= offset_to_data
        strs.append(load_4b_length_prefixed_string(end, data[str_off:]))

    return strs, ('fnv1a_64' if uses_hashes else None)


# This is string.punctuation but with `.` and `-` swapped.
# This change is necessary to get correct output for Kirby Star Allies.
# I have no idea why HAL sorts strings weirdly.
STRING_SORTING_PUNCTUATION_TABLE = '!"#$%&\'()*+,.-/:;<=>?@[\]^_`{|}~'


def fdgh_string_sorting_key(s: str) -> Any:
    """
    Function that can be used to sort strings the same way HAL's tool does
    """
    key = []
    for c in s.lower():
        # Oddly, punctuation sorts before everything else in this sorting scheme,
        # and punctuation isn't even sorted according to ASCII
        if c in STRING_SORTING_PUNCTUATION_TABLE:
            key.append(STRING_SORTING_PUNCTUATION_TABLE.index(c) - 999999999999999)
        else:
            key.append(ord(c))

    return key


def load_xbin(data: bytes) -> (Endianness, bytes, int, int):
    """
    Load the data from this XBIN file.
    Returns the endianness ('>' or '<'), the data, the metadata value
    (as an int), and the XBIN version.
    """
    if len(data) < 16:
        raise ValueError('File is too short for XBIN')

    end = {XBIN_MAGIC_BE: '>', XBIN_MAGIC_LE: '<'}.get(data[:6])
    if end is None:
        raise ValueError('Incorrect XBIN magic')

    version = data[6]
    if data[7] != 0:
        raise ValueError(f'XBIN[7] is {data[7]} (!= 0)')

    # Metadata is always either 0x3A4 or 0xFDE9
    # Please find out what those mean.

    if version == 2:
        data_start = 0x10

        filesize, metadata = struct.unpack_from(end + '2I', data, 8)

    elif version in {4, 5}:
        data_start = 0x14

        filesize, metadata, colr_offset = struct.unpack_from(end + '3I', data, 8)

        filesize_aligned = (filesize + 3) & ~3

        if filesize_aligned != colr_offset:
            raise ValueError(f'XBIN: filesize ({hex(filesize)})'
                             f' != COLR offset ({hex(colr_offset)})')

        if end == '>':
            expected_colr = b'COLR' + b'\0' * 8
        else:
            expected_colr = b'RLOC' + b'\0' * 8

        assert data[colr_offset:] == expected_colr

    else:
        raise ValueError(f'Unknown XBIN version: {version}')

    return end, data[data_start:filesize], metadata, version


def save_xbin(end: Endianness, data: bytes, metadata: int, version: int) -> bytes:
    """
    Create a XBIN file of given version with the provided endianness
    ('>' or '<'), data, and metadata value.
    """
    xbin = bytearray({'>': XBIN_MAGIC_BE, '<': XBIN_MAGIC_LE}[end])
    xbin.append(version)
    xbin.append(0)

    if version == 2:
        header_len = 0x10
    elif version in {4, 5}:
        header_len = 0x14
    else:
        raise ValueError(f'Unknown XBIN version: {version}')

    xbin.extend(struct.pack(end + '2I', header_len + len(data), metadata))

    if version in {4, 5}:
        xbin.extend(b'\0\0\0\0')  # actual value filled in later

    xbin.extend(data)
    while len(xbin) % 4:
        xbin.append(0)

    if version in {4, 5}:
        struct.pack_into(end + 'I', xbin, 0x10, len(xbin))

        xbin.extend(b'COLR' if end == '>' else b'RLOC')
        xbin.extend(b'\0' * 8)

    return bytes(xbin)


def fdgh_to_xml(data: bytes, xbin_version: int) -> str:
    """
    Convert binary FDGH data to a string containing an XML file.
    """

    if len(data) < 16:
        raise ValueError('File is too short to be FDGH')

    # Calculate the adjustment needed for all offset values due to the
    # XBIN header size
    xbin_adj = {
        2: -0x10,
        4: -0x14,
        5: -0x14,
        }.get(xbin_version)
    if xbin_adj is None:
        raise ValueError(f'Unknown XBIN version: {xbin_version}')

    # Main header: 20 bytes
    end = {FDGH_MAGIC_BE: '>', FDGH_MAGIC_LE: '<'}.get(data[:4])
    if end is None:
        raise ValueError('Incorrect FDGH magic')
    (world_map_unknown, world_map_start, room_offset_list_start,
        asset_offset_list_start) = struct.unpack_from(end + '4I', data, 4)

    # World map data: 4b count, then the values themselves
    world_map_count = unpack_u32_from(end, data, world_map_start + xbin_adj)
    world_map_indices = list(struct.unpack_from(
        f'{end}{world_map_count}I', data, world_map_start + 4 + xbin_adj))

    # Room list: 4b count, then three offsets per room, then the data
    # region the offsets point to
    room_list = [] # [('room_name',
                   #   [asset_index, asset_index],
                   #   [link_index, link_index]   )]
    room_count = unpack_u32_from(end, data, room_offset_list_start + xbin_adj)
    for i in range(room_count):

        # Read the three offsets for this room
        start_of_string, start_of_links, start_of_assets = struct.unpack_from(
            end + 'III', data, room_offset_list_start + 4 + 12 * i + xbin_adj)

        # First offset: room name
        room_name = load_4b_length_prefixed_string(end, data[start_of_string + xbin_adj:])

        # Second offset: links to rooms with required assets (indices)
        links_count = unpack_u32_from(end, data, start_of_links + xbin_adj)
        links = []
        for j in range(links_count):
            idx = unpack_u32_from(end, data, start_of_links + 4 + 4 * j + xbin_adj)
            links.append(idx)

        # Third offset: links to required assets (indices)
        assets_count = unpack_u32_from(end, data, start_of_assets + xbin_adj)
        assets = []
        for j in range(assets_count):
            idx = unpack_u32_from(end, data, start_of_assets + 4 + 4 * j + xbin_adj)
            assets.append(idx)

        # Put them in the room list
        room_list.append((room_name, links, assets))

    # Assets list
    assets_list, asset_name_hash_type = load_string_list(
        end, data[asset_offset_list_start + xbin_adj:], asset_offset_list_start)

    ################################################################
    ######################### Generate XML #########################

    root = etree.Element('fdgh')
    root.attrib['endian'] = {'>': 'big', '<': 'little'}[end]
    root.attrib['xbin_version'] = str(xbin_version)
    if asset_name_hash_type is None:
        root.attrib['num_string_null_terminators'] = '4'
    else:
        root.attrib['num_string_null_terminators'] = '1'
        root.attrib['asset_name_hashes'] = asset_name_hash_type

    # Comment
    root.append(etree.Comment(XML_COMMENT.format(datetime.datetime.now())))

    # World map
    world_map_node = etree.SubElement(root, 'worldmap',
        attrib={'value': str(world_map_unknown)})
    for idx in world_map_indices:
        room_node = etree.SubElement(world_map_node, 'room')
        room_node.text = room_list[idx][0]

    # Rooms
    rooms_node = etree.SubElement(root, 'rooms')
    for room_name, link_indices, asset_indices in room_list:
        room_node = etree.SubElement(rooms_node, 'room',
            attrib={'name': room_name})
        for link_index in link_indices:
            link_node = etree.SubElement(room_node, 'link')
            link_node.text = room_list[link_index][0] # The name of the
                                                      # room this link
                                                      # points to
        for asset_index in asset_indices:
            asset_node = etree.SubElement(room_node, 'asset')
            asset_node.text = assets_list[asset_index]

    # Return well-formed UTF-8 XML
    if hasattr(etree, 'indent'):  # new in Python 3.9
        etree.indent(root)

    return etree.tostring(root, encoding='unicode', xml_declaration=True)


def xml_to_fdgh(data: str) -> bytes:
    """
    Convert a string containing an XML file to binary FDGH data.
    """

    world_map_room_names = []
    room_list = []

    fdgh_root = etree.fromstring(data)
    end = {'big': '>', 'little': '<'}.get(
        fdgh_root.attrib.get('endian', 'big'), '>')
    xbin_version = int(fdgh_root.attrib.get('xbin_version', '2'))
    num_string_null_terminators = int(fdgh_root.attrib.get('num_string_null_terminators', 4))
    asset_name_hash_type = fdgh_root.attrib.get('asset_name_hashes')
    if asset_name_hash_type not in {None, 'fnv1a_64'}:
        raise ValueError(f'Unsupported hash type: {asset_name_hashes}')

    for container in fdgh_root:
        if container.tag == 'worldmap':
            # Parse world map data

            world_map_unknown = int(container.get(
                'value', DEFAULT_WORLDMAP_UNKNOWN_VALUE))

            for room in container:
                if room.tag == 'room':
                    world_map_room_names.append(room.text.strip())

        elif container.tag == 'rooms':
            # Parse room data

            for room in container:
                room_name = room.attrib['name']

                link_names = []
                asset_names = []
                for room_subnode in room:
                    if room_subnode.tag == 'link':
                        link_names.append(room_subnode.text.strip())
                    elif room_subnode.tag == 'asset':
                        asset_names.append(room_subnode.text.strip())

                room_list.append((room_name, link_names, asset_names))


    ################################################################
    ######################### Generate FDGH ########################

    # This is difficult to do cleanly because this file uses absolute
    # offsets everywhere. We'll do the best we can.

    # Step 0: calculate the adjustment needed for all offset values due
    # to the XBIN header size
    xbin_adj = {
        2: 0x10,
        4: 0x14,
        5: 0x14,
        }.get(xbin_version)
    if xbin_adj is None:
        raise ValueError(f'Unknown XBIN version: {xbin_version}')

    # Step 1: start putting together a FDGH header
    # That hardcoded value is the offset to the world map data, which is
    # always at 0x24
    magic = FDGH_MAGIC_BE if end == '>' else FDGH_MAGIC_LE
    wm_data_offset = pack_u32(end, 0x14 + xbin_adj)
    fdgh_head = magic + pack_u32(end, world_map_unknown) + wm_data_offset

    # Step 2: put together the world map data
    world_map_data = pack_u32(end, len(world_map_room_names))
    for name in world_map_room_names:
        # Find the index of this name
        for index, (room_name, _, _) in enumerate(room_list):
            if room_name == name:
                world_map_data += pack_u32(end, index)
                break
        else:
            raise ValueError(f'Cannot find the room "{name}", which is'
                              ' referenced in the world map section.')

    # Step 3: generate the assets list (the set-union of all assets
    # needed by all rooms)
    assets_list = []
    for room_name, link_names, asset_names in room_list:
        for asset in asset_names:
            if asset not in assets_list:
                assets_list.append(asset)
    assets_list.sort(key=fdgh_string_sorting_key)

    # Step 4: add the offset to the room-offset list and room data to
    # the header
    offset_to_room_header_data = 0x14 + len(world_map_data) + xbin_adj
    fdgh_head += pack_u32(end, offset_to_room_header_data)
    offset_to_room_data = offset_to_room_header_data + 4 + len(room_list) * 12

    # Step 5: generate the data for each room and the offsets-list for
    # it
    room_offset_data = pack_u32(end, len(room_list))
    room_data = b''
    for room_name, link_names, asset_names in room_list:

        # Room name
        room_offset_data += pack_u32(end, offset_to_room_data + len(room_data))
        room_data += pack_4b_length_prefixed_padded_string(end, room_name, num_string_null_terminators)

        # Link names
        room_offset_data += pack_u32(end, offset_to_room_data + len(room_data))
        room_data += pack_u32(end, len(link_names))
        for name in link_names:
            # Find the index of the level with this name
            for other_idx, (other_name, _, _) in enumerate(room_list):
                if other_name == name:
                    break
            else:
                raise ValueError(f'Cannot find the room matching "{name}".')

            # Append this index as a U32
            room_data += pack_u32(end, other_idx)

        # Asset names
        room_offset_data += pack_u32(end, offset_to_room_data + len(room_data))
        room_data += pack_u32(end, len(asset_names))
        for name in asset_names:
            room_data += pack_u32(end, assets_list.index(name))

    # Assets offset data needs to be aligned to 8, but only for KatFL
    if asset_name_hash_type is not None:
        while (len(fdgh_head) + len(world_map_data) + len(room_offset_data) + len(room_data)) % 8:
            room_data += b'\0'

    # Step 6: add the offset to the assets list to the header
    offset_to_assets_header_list = offset_to_room_data + len(room_data)
    fdgh_head += pack_u32(end, offset_to_assets_header_list)
    if asset_name_hash_type == 'fnv1a_64':
        offset_to_assets_list = offset_to_assets_header_list + 4 + len(assets_list) * 16
    else:
        offset_to_assets_list = offset_to_assets_header_list + 4 + len(assets_list) * 4

    # Step 7: generate the assets list itself
    assets_offset_data = pack_u32(end, len(assets_list))
    assets_data = b''
    for asset in assets_list:
        if asset_name_hash_type == 'fnv1a_64':
            assets_offset_data += b'\0\0\0\0'
            assets_offset_data += pack_u64(end, fnv1a_64(asset.encode('latin-1')))
        assets_offset_data += pack_u32(end, offset_to_assets_list + len(assets_data))
        assets_data += pack_4b_length_prefixed_padded_string(end, asset, num_string_null_terminators)

    # Step 8: put it all together
    return (end,
            fdgh_head + world_map_data + room_offset_data + room_data
                + assets_offset_data + assets_data,
            xbin_version)


def get_output_path(args: argparse.Namespace, auto_suffix: str) -> Path:
    """
    Assumes that args contains a required "input_file" arg, an optional
    "output_file" one, and an "--overwrite" flag that dictates whether
    an auto-generated filename is allowed to overwrite an existing file.

    Get the appropriate output file path, or raise an error if the
    overwrite rule would be violated.
    """
    if args.output_file is None:
        output_fp = args.input_file.with_suffix(auto_suffix)
        if output_fp.is_file() and not args.overwrite:
            raise ValueError(f'Auto-selected output filename "{output_fp}" already exists, and --overwrite wasn\'t specified')
        return output_fp

    else:
        return args.output_file


def main(argv:List[str]=None) -> None:
    """
    Main method run automatically when this module is invoked as a
    script
    """
    parser = argparse.ArgumentParser(
        description='FDGH Converter: Convert FDGH files from Kirby games to/from XML.')

    parser.add_argument('input_file', type=Path,
        help='input file (FDGH or XML)')
    parser.add_argument('output_file', nargs='?', type=Path,
        help='output file (XML or FDGH)')
    parser.add_argument('--overwrite', action='store_true',
        help="overwrite the output file if it already exists (only needed if an output filename isn't explicitly specified)")

    args = parser.parse_args(argv)

    # Auto-detect input file format with some heuristics
    with args.input_file.open('rb') as f:
        first_1024 = f.read(1024)
    input_is_xbin = (first_1024.startswith(XBIN_MAGIC)
        and any(magic in first_1024 for magic in {FDGH_MAGIC_BE, FDGH_MAGIC_LE})
        and (b'\0' in first_1024))
    input_is_xml = ((b'<fdgh' in first_1024)
        and (b'\0' not in first_1024))

    if not (input_is_xbin ^ input_is_xml):
        raise ValueError('Unrecognized input file format')

    # Get output file path
    output_fp = get_output_path(args, '.xml' if input_is_xbin else '.dat')

    # Perform actual conversion
    if input_is_xbin:
        print('Converting FDGH to XML.')

        xbin_data = args.input_file.read_bytes()

        end, fdgh_data, metadata, xbin_version = load_xbin(xbin_data)
        xml_data = fdgh_to_xml(fdgh_data, xbin_version)

        output_fp.write_text(xml_data, encoding='utf-8')

    else:
        print('Converting XML to FDGH.')

        xml_data = args.input_file.read_text(encoding='utf-8')

        end, fdgh_data, xbin_version = xml_to_fdgh(xml_data)
        xbin_data = save_xbin(end, fdgh_data, 0xFDE9, xbin_version)

        output_fp.write_bytes(xbin_data)

    print('Done.')


if __name__ == '__main__':
    main()
