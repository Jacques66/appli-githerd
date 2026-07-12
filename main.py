# -*- coding: utf-8 -*-
"""
GitHerd — PyInstaller entry point.

A plain .py entry (the CLI launcher `githerd` has no extension, which
PyInstaller dislikes). Keep this thin — it just boots the package.
"""

from githerd_pkg import main

if __name__ == "__main__":
    main()
