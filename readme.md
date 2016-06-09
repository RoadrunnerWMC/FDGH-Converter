# FDGH Converter 1.0

A script that converts Kirby's Return to Dreamland FDGH files to and from XML.
Copyright (C) 2016 RoadrunnerWMC

## FDGH Files

FDGH is a file format used in Kirby's Return to Dreamland which defines which files (models, animations, etc) the game should load in advance of each level. If the game encounters enemies not predicted by the FDGH file, it will still load the enemy's files as needed, but an annoying lag will occur momentarily during gameplay. Thus, the FDGH file needs to be editable for interesting custom levels to be possible.

The game's single FDGH file, located at `<disk_root>/fdg/Archive.dat`, is embedded in a very thin wrapper called an XBIN. While most XBIN files have a .bin extension, this particular one has a .dat extension for reasons unknown.

## Usage

If using a frozen executable, you can simply drag-and-drop `Archive.dat` or `Archive.xml` onto the executable.

If running from source, run fdgh_converter.py with a recent version of Python 3. (Tested on 3.5.1 on Windows.)

* `python3 fdgh_converter.py file.dat`: Converts file.dat to file.xml
* `python3 fdgh_converter.py file.xml`: Converts file.xml to file.dat

## License

Licensed under the GNU General Public License version 3 or (at your option) any later version. (See the "COPYING" file for more information.)
