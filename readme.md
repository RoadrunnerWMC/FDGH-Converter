# FDGH Converter 3.0

A script that converts FDGH files (found in several Kirby games) to and from XML.
Copyright (C) 2016-2018 RoadrunnerWMC

## FDGH Files

FDGH is a file format used in various Kirby games that defines which files (models, animations, etc) the game should load in advance of each level. If a level calls for enemies not foretold by the FDGH file, the game will either lag (Return to Dreamland) or crash (Triple Deluxe, Robobot). Thus, the FDGH file needs to be editable for interesting custom levels to be possible.

Kirby's Return to Dreamland's single FDGH file, located at `<disk_root>/fdg/Archive.dat`, is embedded in a very thin wrapper called an XBIN. While most XBIN files have a .bin extension, this particular one has a .dat extension for reasons unknown.

Kirby's Return to Dreamland uses big-endian XBIN and FDGH files, and Kirby Triple Deluxe through Kirby Star Allies use little-endian XBIN and FDGH files. Endianness is detected automatically when converting FDGH to XML, and can be specified using the "endian" attribute of the root XML node when converting back. (Valid values: "big", "little". For backward-compatibility, the default is "big" if unspecified.)

Kirby Battle Royale and Kirby Star Allies use version "4" XBIN files; earlier games use version "2". This can be specified using the "xbin_version" attribute of the root XML node. (Only versions 2 and 4 are supported. The default is "2" for backward-compatibility.)

## Usage

If using a frozen executable, you can simply drag-and-drop `Archive.dat` or `Archive.xml` onto the executable.

If running from source, run fdgh_converter.py with Python 3.6 or newer. (Tested on 3.6.5 on Ubuntu.)

* `python3 fdgh_converter.py file.dat`: Converts file.dat to file.xml
* `python3 fdgh_converter.py file.xml`: Converts file.xml to file.dat

## License

Licensed under the GNU General Public License version 3 or (at your option) any later version. (See the "COPYING" file for more information.)
