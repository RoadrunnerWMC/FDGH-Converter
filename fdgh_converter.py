#!/usr/bin/python
"""
FDGH Converter 2.0
A script that converts FDGH files (found in several Kirby games) to and
from XML.
Copyright (C) 2016-2017 RoadrunnerWMC

FDGH Converter is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

FDGH Converter is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with FDGH Converter.  If not, see <http://www.gnu.org/licenses/>.

~~~~

FDGH is a file format used in various Kirby games that defines which
files (models, animations, etc) the game should load in advance of each
level. If a level calls for enemies not foretold by the FDGH file, the
game will either lag (Return to Dreamland) or crash (Triple Deluxe,
Robobot). Thus, the FDGH file needs to be editable for interesting
custom levels to be possible.

Kirby's Return to Dreamland's single FDGH file, located at
<disk_root>/fdg/Archive.dat, is embedded in a very thin wrapper called
an XBIN. While most XBIN files have a .bin extension, this particular
one has a .dat extension for reasons unknown.

Kirby's Return to Dreamland uses big-endian XBIN and FDGH files, and
Kirby Triple Deluxe and Kirby Planet Robobot use little-endian XBIN and
FDGH files. Endianness is detected automatically when converting FDGH to
XML, and can be specified using the "endian" attribute in the root XML
node when converting back. (Valid values: "big", "little". For backward-
-compatibility, the default is "big" if unspecified.)

Usage:
python3 fdgh_converter.py file.dat    Converts file.dat to file.xml
python3 fdgh_converter.py file.xml    Converts file.xml to file.dat
"""


import datetime
import struct
import sys
from xml.etree import ElementTree as etree


DEFAULT_WORLDMAP_UNKNOWN_VALUE = 2
XBIN_MAGIC_BE = b'XBIN\x124\2\0'
XBIN_MAGIC_LE = b'XBIN4\x12\2\0'
FDGH_MAGIC_BE = b'FDGH'
FDGH_MAGIC_LE = b'HGDF'


# These make the code look cleaner!
unpackU32 = lambda end, *args: struct.unpack(end + 'I', *args)[0]
unpackU32_from = lambda end, *args: struct.unpack_from(end + 'I', *args)[0]
packU32 = lambda end, *args: struct.pack(end + 'I', *args)


def load4bLengthPrefixedString(end, data):
    """
    Load a 4-byte length prefixed string.
    """
    strLen = unpackU32(end, data[:4])
    return data[4:4+strLen].decode('latin-1')


def pack4bLengthPrefixedPaddedString(end, string):
    """
    Pack a 4-byte length prefixed string.
    These files add 4 bytes of null padding to the end of each of these
    strings, and *then* pad to multiples of 4 (so, 4-7 bytes of padding
    total). This function replicates that behavior.
    """
    encoded = packU32(end, len(string))
    encoded += string.encode('latin-1')
    encoded += b'\0\0\0\0'
    while len(encoded) % 4:
        encoded += b'\0'
    return encoded


def loadStringList(end, data, offsetToData):
    """
    Load a string list. This consists of a 4-byte string count (call it
    "n"), followed by n offsets, followed by the data region the offsets
    point to. Each offset points to a 4-byte length-prefixed string.

    The offsetToData parameter is the absolute offset of the data being
    passed. This is needed in order to convert the absolute offsets of
    the string-offsets section into relative offsets, which can be
    loaded correctly.
    """
    numberOfStrings = unpackU32(end, data[:4])

    strs = []
    for i in range(numberOfStrings):
        strOff = unpackU32_from(end, data, 4 + 4 * i)
        strOff -= offsetToData
        strs.append(load4bLengthPrefixedString(end, data[strOff:]))

    return strs


def loadXbin(data):
    """
    Load the data from this XBIN file.
    Returns the endianness ('>' or '<'), the data, and the metadata
    value (as an int).
    """
    if len(data) < 16:
        raise ValueError('File is too short for XBIN')

    end = {XBIN_MAGIC_BE: '>', XBIN_MAGIC_LE: '<'}.get(data[:8])
    if end is None:
        raise ValueError('Incorrect XBIN magic')

    filesize, metadata = struct.unpack_from(end + '2I', data, 8)

    # Metadata is always either 0x3A4 or 0xFDE9
    # Please find out what those mean.

    return end, data[16:filesize], metadata


def saveXbin(end, data, metadata):
    """
    Create a XBIN file with the provided endianness ('>' or '<'), data,
    and metadata value.
    """
    magic = {'>': XBIN_MAGIC_BE, '<': XBIN_MAGIC_LE}[end]
    return magic + struct.pack(end + '2I', len(data) + 16, metadata) + data


def fdghToXml(data):
    """
    Convert binary FDGH data to a string containing an XML file.
    """

    if len(data) < 16:
        raise ValueError('File is too short to be FDGH')

    # Main header: 20 bytes
    end = {FDGH_MAGIC_BE: '>', FDGH_MAGIC_LE: '<'}.get(data[:4])
    if end is None:
        raise ValueError('Incorrect FDGH magic')
    (worldMapUnknown, worldMapStart, roomOffsetListStart,
        assetOffsetListStart) = struct.unpack_from(end + '4I', data, 4)

    # World map data: 4b count, then the values themselves
    worldMapCount = unpackU32_from(end, data, worldMapStart - 16)
    worldMapIndices = list(struct.unpack_from(
        end + '%dI' % worldMapCount, data, worldMapStart - 12))

    # Room list: 4b count, then three offsets per room, then the data
    # region the offsets point to
    roomList = [] # [('roomName',
                  #   [assetIndex, assetIndex],
                  #   [linkIndex, linkIndex]   )]
    roomCount = unpackU32_from(end, data, roomOffsetListStart - 16)
    for i in range(roomCount):

        # Read the three offsets for this room
        startOfString, startOfLinks, startOfAssets = struct.unpack_from(
            end + 'III', data, roomOffsetListStart - 12 + 12 * i)

        # First offset: room name
        roomName = load4bLengthPrefixedString(end, data[startOfString - 16:])

        # Second offset: links to rooms with required assets (indices)
        linksCount = unpackU32_from(end, data, startOfLinks - 16)
        links = []
        for i in range(linksCount):
            idx = unpackU32_from(end, data, startOfLinks - 12 + 4 * i)
            links.append(idx)

        # Third offset: links to required assets (indices)
        assetsCount = unpackU32_from(end, data, startOfAssets - 16)
        assets = []
        for i in range(assetsCount):
            idx = unpackU32_from(end, data, startOfAssets - 12 + 4 * i)
            assets.append(idx)

        # Put them in the room list
        roomList.append((roomName, links, assets))

    # Assets list
    assetsList = loadStringList(
        end, data[assetOffsetListStart-16:], assetOffsetListStart)

    ################################################################
    ######################### Generate XML #########################

    root = etree.Element('fdgh')
    root.attrib['endian'] = {'>': 'big', '<': 'little'}[end]

    # Comment
    root.append(etree.Comment('This XML file was generated on '
                              + str(datetime.datetime.now())
                              + ' by:'
                              + __doc__))

    # World map
    worldMapNode = etree.SubElement(root, 'worldmap',
        attrib={'value': str(worldMapUnknown)})
    for idx in worldMapIndices:
        roomNode = etree.SubElement(worldMapNode, 'room')
        roomNode.text = roomList[idx][0]

    # Rooms
    roomsNode = etree.SubElement(root, 'rooms')
    for roomName, linkIndices, assetIndices in roomList:
        roomNode = etree.SubElement(roomsNode, 'room',
            attrib={'name': roomName})
        for linkIndex in linkIndices:
            linkNode = etree.SubElement(roomNode, 'link')
            linkNode.text = roomList[linkIndex][0] # The name of the
                                                   # room this link
                                                   # points to
        for assetIndex in assetIndices:
            assetNode = etree.SubElement(roomNode, 'asset')
            assetNode.text = text=assetsList[assetIndex]

    # Return well-formed UTF-8 XML
    return ('<?xml version="1.0" encoding="utf-8"?>'
            + etree.tostring(root, encoding='unicode'))


def xmlToFdgh(data):
    """
    Convert a string containing an XML file to binary FDGH data.
    """

    worldMapRoomNames = []
    roomList = []

    fdghRoot = etree.fromstring(data)
    end = {'big': '>', 'little': '<'}.get(
        fdghRoot.attrib.get('endian', 'big'), '>')
    for container in fdghRoot:
        if container.tag == 'worldmap':
            # Parse world map data

            worldMapUnknown = int(container.get(
                'value', DEFAULT_WORLDMAP_UNKNOWN_VALUE))

            for room in container:
                if room.tag == 'room':
                    worldMapRoomNames.append(room.text.strip())

        elif container.tag == 'rooms':
            # Parse room data

            for room in container:
                roomName = room.attrib['name']

                linkNames = []
                assetNames = []
                for roomSubnode in room:
                    if roomSubnode.tag == 'link':
                        linkNames.append(roomSubnode.text.strip())
                    elif roomSubnode.tag == 'asset':
                        assetNames.append(roomSubnode.text.strip())

                roomList.append((roomName, linkNames, assetNames))


    ################################################################
    ######################### Generate FDGH ########################

    # This is difficult to do cleanly because this file uses absolute
    # offsets everywhere. We'll do the best we can.

    # Step 1: start putting together a FDGH header
    # That hardcoded value is the offset to the world map data, which is
    # always at 0x24
    magic = FDGH_MAGIC_BE if end == '>' else FDGH_MAGIC_LE
    wmDataOffset = b'\0\0\0$' if end == '>' else b'$\0\0\0'
    fdghHead = magic + packU32(end, worldMapUnknown) + wmDataOffset

    # Step 2: put together the world map data
    worldMapData = packU32(end, len(worldMapRoomNames))
    for name in worldMapRoomNames:
        # Find the index of this name
        for index, (roomName, _, _) in enumerate(roomList):
            if roomName == name:
                worldMapData += packU32(end, index)
                break
        else:
            raise ValueError('Cannot find the room "%s", which is'
                ' referenced in the world map section.' % name)

    # Step 3: generate the assets list (the set-union of all assets
    # needed by all rooms)
    assetsList = []
    for roomName, linkNames, assetNames in roomList:
        for asset in assetNames:
            if asset not in assetsList:
                assetsList.append(asset)

    # Step 4: add the offset to the room-offset list and room data to
    # the header
    offsetToRoomHeaderData = 0x24 + len(worldMapData)
    fdghHead += packU32(end, offsetToRoomHeaderData)
    offsetToRoomData = offsetToRoomHeaderData + 4 + len(roomList) * 12

    # Step 5: generate the data for each room and the offsets-list for
    # it
    roomOffsetData = packU32(end, len(roomList))
    roomData = b''
    for roomName, linkNames, assetNames in roomList:

        # Room name
        roomOffsetData += packU32(end, offsetToRoomData + len(roomData))
        roomData += pack4bLengthPrefixedPaddedString(end, roomName)

        # Link names
        roomOffsetData += packU32(end, offsetToRoomData + len(roomData))
        roomData += packU32(end, len(linkNames))
        for name in linkNames:
            # Find the index of the level with this name
            for otherIdx, (otherName, _, _) in enumerate(roomList):
                if otherName == name:
                    break
            else:
                raise ValueError('Cannot find the room matching "%s".' % name)

            # Append this index as a U32
            roomData += packU32(end, otherIdx)

        # Asset names
        roomOffsetData += packU32(end, offsetToRoomData + len(roomData))
        roomData += packU32(end, len(assetNames))
        for name in assetNames:
            roomData += packU32(end, assetsList.index(name))

    # Step 6: add the offset to the assets list to the header
    offsetToAssetsHeaderList = offsetToRoomData + len(roomData)
    fdghHead += packU32(end, offsetToAssetsHeaderList)
    offsetToAssetsList = offsetToAssetsHeaderList + 4 + len(assetsList) * 4

    # Step 7: generate the assets list itself
    assetsOffsetData = packU32(end, len(assetsList))
    assetsData = b''
    for asset in assetsList:
        assetsOffsetData += packU32(end, offsetToAssetsList + len(assetsData))
        assetsData += pack4bLengthPrefixedPaddedString(end, asset)

    # Step 8: put it all together
    return (end, fdghHead + worldMapData + roomOffsetData + roomData
                 + assetsOffsetData + assetsData)


def main(argv):
    """
    Main method run automatically when this module is invoked as a
    script
    """
    print(__doc__)

    if len(argv) != 2:
        print('ERROR: incorrect number of command-line arguments'
            ' (expected 2, got %d)' % len(argv))
        return

    inputFile = argv[1]

    if inputFile.endswith('.dat'):
        # Convert FDGH to XML
        print('Converting FDGH to XML.')

        with open(inputFile, 'rb') as f:
            xbinData = f.read()

        end, fdghData, metadata = loadXbin(xbinData)
        xmlData = fdghToXml(fdghData)

        with open(inputFile[:-4] + '.xml', 'w', encoding='utf-8') as f:
            f.write(xmlData)

    elif inputFile.endswith('.xml'):
        # Convert XML to FDGH
        print('Converting XML to FDGH.')

        with open(inputFile, 'r', encoding='utf-8') as f:
            xmlData = f.read()

        end, fdghData = xmlToFdgh(xmlData)
        xbinData = saveXbin(end, fdghData, 0xFDE9)

        with open(inputFile[:-4] + '.dat', 'wb') as f:
            f.write(xbinData)

    else:
        print('ERROR: the input filename does not end with ".dat" or'
            ' ".xml" (it ends with "%s")' % inputFile[-4:])
        return

    print('Done.')


if __name__ == '__main__': main(sys.argv)
