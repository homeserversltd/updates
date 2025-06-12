"""
HOMESERVER Update Management System
Copyright (C) 2024 HOMESERVER LLC

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

"""
Oh My Posh Update Module

Handles update logic specific to the Oh My Posh service.
Implements a main(args) entrypoint for orchestrated updates.
"""

import os
from ...utils.index import get_module_version
from .index import main  # Expose main at package level

__version__ = get_module_version(os.path.dirname(os.path.abspath(__file__)))

__all__ = ['main']

if __name__ == "__main__":
    import sys
    main(sys.argv[1:] if len(sys.argv) > 1 else [])
