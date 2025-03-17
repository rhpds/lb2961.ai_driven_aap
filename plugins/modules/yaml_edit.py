#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright 2023
# Licensed under the MIT License (or choose an appropriate license)

DOCUMENTATION = r'''
---
module: yaml_edit
short_description: Safely edit specific keys/indices in a YAML file while preserving formatting
description:
  - This module updates specified keys or list indices in an existing YAML file using ruamel.yaml to preserve
    formatting, comments, and structure as much as possible.
  - Keys can be nested via dot notation (C(some.nested.key)) or bracket notation for lists (C(mylist[0]))
    or dictionaries with bracketed keys (C(mydict["complex.key"])).
  - If the file does not exist, an empty YAML structure is created before applying changes.
options:
  path:
    description:
      - Path to the YAML file to edit.
    required: true
    type: str
  changes:
    description:
      - A mapping of "key paths" to the desired values.
      - Example:
        C({
          "some.nested.key": "value",
          "mylist[0]": "changed first item"
        })
    required: true
    type: dict
  backup:
    description:
      - Whether to create a backup of the file before editing.
    required: false
    default: false
    type: bool
author:
  - Your Name <you@example.com>
'''

EXAMPLES = r'''
- name: Update a nested dictionary key
  yaml_edit:
    path: /etc/myapp/config.yaml
    changes:
      parent.child.key: "new_value"

- name: Update list items
  yaml_edit:
    path: /etc/myapp/config.yaml
    changes:
      mylist[0]: "first element"
      mylist[1]: "second element"
    backup: true

- name: Mix dictionary and list usage
  yaml_edit:
    path: /etc/myapp/config.yaml
    changes:
      serve.vllm.vllm_args[0]: --tensor-parallel-size
      serve.vllm.vllm_args[1]: '5'
      serve.vllm.vllm_args[2]: --api-key
'''

RETURN = r'''
changed:
  description: Indicates if the file was modified.
  type: bool
  returned: always
msg:
  description: Description of any changes made or errors encountered.
  type: str
  returned: always
'''

import os
import copy
from ansible.module_utils.basic import AnsibleModule

# Attempt to load ruamel.yaml
try:
    from ruamel.yaml import YAML
    HAS_RUAMEL = True
except ImportError:
    HAS_RUAMEL = False


def parse_key_path(key_path):
    """
    Parse a key path string into a list of segments.
    Supports:
      - Dot notation: parent.child
      - Bracket notation: parent[0], parent["some.key"]
    Returns a list of segments, where integers are list indices and strings are dict keys.

    Example:
      "serve.vllm.vllm_args[1]" -> ["serve", "vllm", "vllm_args", 1]
      "parent.child[\"key\"]"   -> ["parent", "child", "key"]
    """
    segments = []
    current_segment = ""
    in_brackets = False
    i = 0

    while i < len(key_path):
        char = key_path[i]

        if char == '.' and not in_brackets:
            # Dot outside brackets => split
            if current_segment:
                segments.append(current_segment)
            current_segment = ""
        elif char == '[':
            # Bracket starts => add current segment if any, parse bracket content separately
            if current_segment:
                segments.append(current_segment)
            current_segment = ""
            in_brackets = True
        elif char == ']':
            # Bracket ends
            in_brackets = False
            bracket_content = current_segment.strip('"').strip("'").strip()
            # Try to interpret bracket_content as an integer
            try:
                bracket_index = int(bracket_content)
                segments.append(bracket_index)
            except ValueError:
                # Not an integer => treat it as a string
                segments.append(bracket_content)
            current_segment = ""
        else:
            current_segment += char
        i += 1

    # Append leftover if any
    if current_segment:
        segments.append(current_segment)

    return segments


def ensure_list_size(lst, index):
    """
    Ensure 'lst' has at least 'index+1' items, padding with None if needed.
    """
    while len(lst) <= index:
        lst.append(None)


def set_nested_value(data, key_path, value, module):
    """
    Traverse or create nested structures (dicts/lists) according to
    the parsed path, then set the final key/index to 'value'.

    - Dot notation => dictionary keys
    - Bracket notation with int => list index
    - Bracket notation with string => dictionary key
    """
    segments = parse_key_path(key_path)
    ref = data
    for seg in segments[:-1]:
        if isinstance(seg, int):
            # This segment is a list index
            if not isinstance(ref, list):
                # If it's not a list, we can decide to convert or fail
                ref_type = type(ref).__name__
                if ref_type == 'dict' and len(ref) == 0:
                    # Convert empty dict to list
                    ref = []
                else:
                    module.fail_json(msg=f"Expected a list at segment {seg}, found {ref_type}")
            ensure_list_size(ref, seg)
            if ref[seg] is None:
                # Initialize as a dict by default, or list, depending on your logic
                ref[seg] = {}
            ref = ref[seg]
        else:
            # This segment is a dictionary key
            if not isinstance(ref, dict):
                # Convert or fail
                ref_type = type(ref).__name__
                if ref_type == 'list' and len(ref) == 0:
                    # Convert empty list to dict
                    ref = {}
                else:
                    module.fail_json(msg=f"Expected a dict at segment '{seg}', found {ref_type}")
            if seg not in ref:
                ref[seg] = {}
            ref = ref[seg]

    last_seg = segments[-1]
    if isinstance(last_seg, int):
        # Final segment is a list index
        if not isinstance(ref, list):
            ref_type = type(ref).__name__
            module.fail_json(msg=f"Expected a list for final segment {last_seg}, found {ref_type}")
        ensure_list_size(ref, last_seg)
        ref[last_seg] = value
    else:
        # Final segment is a dict key
        if not isinstance(ref, dict):
            ref_type = type(ref).__name__
            module.fail_json(msg=f"Expected a dict for final segment '{last_seg}', found {ref_type}")
        ref[last_seg] = value


def main():
    module = AnsibleModule(
        argument_spec=dict(
            path=dict(type='str', required=True),
            changes=dict(type='dict', required=True),
            backup=dict(type='bool', required=False, default=False)
        ),
        supports_check_mode=True
    )

    # Check if ruamel.yaml is available
    if not HAS_RUAMEL:
        module.fail_json(msg="The 'ruamel.yaml' library is required. Install it via pip (e.g. pip install ruamel.yaml).")

    path = module.params['path']
    changes = module.params['changes']
    backup = module.params['backup']

    # Initialize YAML parser
    try:
        yaml = YAML()
        yaml.preserve_quotes = True
        yaml.explicit_start = False
        yaml.indent(sequence=4, offset=2)
    except Exception as e:
        module.fail_json(msg=f"Error initializing YAML parser: {e}")

    # Load or initialize data
    original_data = {}
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                loaded_data = yaml.load(f)
                if loaded_data is None:
                    loaded_data = {}
                original_data = loaded_data
        except Exception as e:
            module.fail_json(msg=f"Failed to parse YAML file '{path}': {e}")
    else:
        # If file doesn't exist, start with an empty dict
        original_data = {}

    updated_data = copy.deepcopy(original_data)

    # Apply changes
    for key_path, val in changes.items():
        try:
            set_nested_value(updated_data, key_path, val, module)
        except Exception as e:
            module.fail_json(msg=f"Error applying change for '{key_path}': {e}")

    # Compare old vs. new
    if updated_data != original_data:
        # Something changed
        if module.check_mode:
            module.exit_json(changed=True, msg="Changes would have been made (check mode).")

        # Backup if requested
        if backup and os.path.exists(path):
            module.backup_local(path)

        # Write updated data
        try:
            with open(path, 'w', encoding='utf-8') as f:
                yaml.dump(updated_data, f)
        except Exception as e:
            module.fail_json(msg=f"Failed to write updates to '{path}': {e}")

        module.exit_json(changed=True, msg=f"File '{path}' updated successfully.")
    else:
        # No changes needed
        module.exit_json(changed=False, msg="No changes were required.")


if __name__ == '__main__':
    main()