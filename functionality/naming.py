"""
This file contains functions for dynamic naming of objects.

Author(s): David Marchant
"""

from typing import List
from random import SystemRandom

from core.correctness.vars import CHAR_LOWERCASE, CHAR_UPPERCASE


#TODO Make this guaranteed unique
def generate_id(prefix:str="", length:int=16, existing_ids:List[str]=[], 
        charset:str=CHAR_UPPERCASE+CHAR_LOWERCASE, attempts:int=24):
    random_length = max(length - len(prefix), 0)
    for _ in range(attempts):
        id = prefix + ''.join(SystemRandom().choice(charset) 
            for _ in range(random_length))
        if id not in existing_ids:
            return id
    raise ValueError(f"Could not generate ID unique from '{existing_ids}' "
        f"using values '{charset}' and length of '{length}'.")