#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test VKAuth module independently"""

import sys
import os

# Set UTF-8 encoding for Windows
if sys.platform == 'win32':
    os.system('chcp 65001 >nul')
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, '.')

from VKLivePointsMiner.classes.VKAuth import VKAuth

# Тест создания объекта
auth = VKAuth()
print("[OK] VKAuth object created")

# Тест проверки авторизации (должен вернуть False если нет session.json)
is_auth = auth.is_authorized()
print(f"[OK] is_authorized() returned: {is_auth}")

print("\n[SUCCESS] All basic tests passed!")
print("\nNext steps:")
print("  1. Run: python run.py --auth")
print("  2. Follow instructions to save cookies")
print("  3. Run: python run.py")
