# -*- coding: utf-8 -*-

import re
import os.path

from enum import IntEnum
from collections import namedtuple
from .marsh import rebase_array


__all__ = ['IntSet', 'FloatSet', 'parse_value', 'dzn2dict']


IntSet = namedtuple('IntSet', ['lb', 'ub'])
FloatSet = namedtuple('FloatSet', ['lb', 'ub'])


# boolean pattern
_bool_p = re.compile('^(?:true|false)$')

# integer pattern
_int_p = re.compile('^[+\-]?\d+$')

# float pattern
_float_p = re.compile('^[+\-]?\d*\.\d+(?:[eE][+\-]?\d+)?$')

# ratio pattern (used in OptiMathSat)
_ratio_p = re.compile('^\s*(?P<numerator>\d+)/(?P<denominator>\d+)$')

# enum value pattern
_enum_val_p = re.compile('^\w+$')

# contiguous set
_cont_set_p = re.compile(
    '^\(?\s*([+\-]?\d+(?:\.\d+)?)\)?\.\.\(?([+\-]?\d+(?:\.\d+)?)\s*\)?$'
)

# set pattern
_set_p = re.compile('^(\{(?P<vals>[\w\d\s,\.+\-\(\)]*)\})$')

# contiguous integer set pattern
_cont_int_set_p = re.compile('^([+\-]?\d+)\.\.([+\-]?\d+)$')

# enum pattern
_enum_p = re.compile('^\{(?P<vals>[\w\s,]*)\}$')

# matches any of the previous
_val_p = re.compile(
    '(?:true|false|[+\-]?\d+|[+\-]?\d*\.\d+(?:[eE][+\-]?\d+)?|\w+'
    '|\(?\s*[+\-]?\d+(?:\.\d+)?\)?\.\.\(?[+\-]?\d+(?:\.\d+)?\s*\)?'
    '|\{[\w\d\s,\.+\-\(\)]*\})'
)

# multi-dimensional array pattern
_array_p = re.compile(
    '^\s*(?:array(?P<dim>\d)d\s*\(\s*'
    '(?P<indices>[\w\d\s\.+\-\(\)\{\}]+(?:\s*,\s*[\w\d\s\.+\-\(\)\{\}]+)*)\s*,'
    '\s*)?\[(?P<vals>[\w\s\.,+\-\\\/\*^|\(\)\{\}]*)\]\)?\s*$'
)

# variable pattern
_var_p = re.compile('^\s*(?P<var>[\w]+)\s*=\s*(?P<val>.+)$', re.DOTALL)

# statement pattern
_stmt_p = re.compile('\s*([^;]+?);')

# comment pattern
_comm_p = re.compile('%.+?\n')


def _parse_bool(val, raise_errors=True):
    if _bool_p.match(val):
        return {'true': True, 'false': False}[val]
    if raise_errors:
        raise ValueError('Value \'{}\' is not a Boolean.'.format(val))
    return None


def _parse_int(val, raise_errors=True):
    if _int_p.match(val):
        return int(val)
    if raise_errors:
        raise ValueError('Value \'{}\' is not a integer.'.format(val))
    return None


def _parse_float(val, raise_errors=True):
    ratio_m = _ratio_p.match(val)
    if ratio_m:
        num = float(ratio_m.group('numerator'))
        den = float(ratio_m.group('denominator'))
        return num / den
    if _float_p.match(val):
        return float(val)
    if raise_errors:
        raise ValueError('Value \'{}\' is not a float.'.format(val))
    return None


def _parse_enum_val(val, var_enum=None, raise_errors=True):
    if _enum_val_p.match(val):
        if var_enum:
            return var_enum[val]
        return val
    if raise_errors:
        raise ValueError('Value \'{}\' is not an enum value.'.format(val))
    return None


def _parse_val_basic_type(val, var_type=None, enums=None, raise_errors=True):

    if not var_type:
        return _parse_val_infer_basic_type(val, raise_errors=raise_errors)

    if 'dims' in var_type:
        if raise_errors:
            raise ValueError(
                'The type \'{}\' belongs to an array.'.format(var_type)
            )
        return None

    if 'set' in var_type and var_type['set']:
        if raise_errors:
            raise ValueError(
                'The type \'{}\' belongs to an array.'.format(var_type)
            )
        return None

    if 'enum_type' in var_type:
        enum_type = var_type['enum_type']
        val_enum = None
        if enums and enum_type in enums:
            val_enum = enums[enum_type]
        return _parse_enum_val(
            val, var_enum=val_enum, raise_errors=raise_errors
        )

    if var_type['type'] == 'bool':
        return _parse_bool(val, raise_errors=raise_errors)

    if var_type['type'] == 'int':
        return _parse_int(val, raise_errors=raise_errors)

    if var_type['type'] == 'float':
        return _parse_float(val, raise_errors=raise_errors)

    if raise_errors:
        raise ValueError('Type \'{}\' not recognized.'.format(var_type))

    return None


def _parse_val_infer_basic_type(val, raise_errors=True):

    if _bool_p.match(val):
        return {'true': True, 'false': False}[val]

    if _int_p.match(val):
        return int(val)

    ratio_m = _ratio_p.match(val)
    if ratio_m:
        num = float(ratio_m.group('numerator'))
        den = float(ratio_m.group('denominator'))
        return num / den

    if _float_p.match(val):
        return float(val)

    if _enum_val_p.match(val):
        return str(val)

    if raise_errors:
        raise ValueError('Could not parse value \'{}\'.'.format(val))

    return None


def _parse_contiguous_set(val, raise_errors=True):
    cont_set_m = _cont_set_p.match(val)
    if cont_set_m:
        lb = cont_set_m.group(1)
        ub = cont_set_m.group(2)
        if _int_p.match(lb):
            lb = int(lb)
            ub = int(ub)
            return IntSet(lb=lb, ub=ub)
        if _float_p.match(lb):
            lb = float(lb)
            ub = float(ub)
            return FloatSet(lb=lb, ub=ub)
        raise ValueError('Could not parse contiguous set \'{}\'.'.format(val))
    if raise_errors:
        raise ValueError('Value \'{}\' is not a contiguous set.'.format(val))
    return None


def _parse_set(val, set_type=None, enums=None, raise_errors=True):
    set_m = _set_p.match(val)
    if set_m:
        vals = set_m.group('vals').strip()
        if vals:
            vals_type = None
            if set_type:
                vals_type = dict(set_type)
                vals_type.pop('set', None)
            return _parse_set_vals(
                vals.split(','), vals_type=vals_type, enums=enums,
                raise_errors=raise_errors
            )
        return set()
    if raise_errors:
        raise ValueError('Value \'{}\' is not a set.'.format(val))
    return None


def _parse_set_vals(vals, vals_type=None, enums=None, raise_errors=True):
    p_s = set()
    for val in vals:
        p_val = val.strip()
        p_val = _parse_val_basic_type(
            p_val, var_type=vals_type, enums=enums, raise_errors=raise_errors
        )
        p_s.add(p_val)
    return p_s


def _parse_enum_vals(vals):
    p_s = []
    for val in vals:
        p_val = val.strip()
        if _enum_val_p.match(p_val):
            p_s.append(p_val)
        else:
            raise ValueError((
                'A value of the input set is not an enum value: {}'
            ).format(repr(p_val)), p_val)
    return p_s


def _parse_val(val, var_type=None, enums=None, raise_errors=True):

    if not var_type:
        return _parse_val_infer_type(val, raise_errors=raise_errors)

    if 'dims' in var_type:
        if raise_errors:
            raise ValueError(
                'Type \'{}\' belongs to an array.'.format(var_type)
            )
        return None

    if 'set' in var_type and var_type['set']:
        if 'enum_type' not in var_type:
            p_val = _parse_contiguous_set(val, raise_errors=False)
            if p_val is not None:
                return p_val
        return _parse_set(
            val, set_type=var_type, enums=enums, raise_errors=raise_errors
        )

    return _parse_val_basic_type(
        val, var_type=var_type, enums=enums, raise_errors=raise_errors
    )


def _parse_val_infer_type(val, raise_errors=True):

    p_val = _parse_val_infer_basic_type(val, raise_errors=False)

    if p_val is not None:
        return p_val

    cont_set_m = _cont_set_p.match(val)
    if cont_set_m:
        lb = cont_set_m.group(1)
        ub = cont_set_m.group(2)
        if _int_p.match(lb):
            lb = int(lb)
            ub = int(ub)
            return IntSet(lb=lb, ub=ub)
        if _float_p.match(lb):
            lb = float(lb)
            ub = float(ub)
            return FloatSet(lb=lb, ub=ub)
        raise ValueError('Could not parse contiguous set \'{}\'.'.format(val))

    set_m = _set_p.match(val)
    if set_m:
        vals = set_m.group('vals').strip()
        if vals:
            return _parse_set_vals(vals.split(','))
        return set()

    if raise_errors:
        raise ValueError('Could not parse value \'{}\'.'.format(val))

    return None


def _parse_array(
    val, rebase_arrays=True, var_type=None, enums=None, raise_errors=True
):
    array_m = _array_p.match(val)
    if array_m:
        vals = array_m.group('vals')
        vals = _val_p.findall(vals)
        dim = array_m.group('dim')
        if dim:  # explicit dimensions
            dim = int(dim)
            indices = array_m.group('indices')
            indices = _parse_indices(indices, enums=enums)
            assert len(indices) == dim
        else:  # assuming 1d array based in 1
            indices = [range(1, len(vals) + 1)]
        if len(vals) == 0:
            p_val = []
        else:
            vals_type = None
            if var_type:
                vals_type = dict(var_type)
                vals_type.pop('dim', None)
                vals_type.pop('dims', None)
            p_val = _parse_array_vals(
                indices, vals, rebase_arrays=rebase_arrays, vals_type=vals_type,
                enums=enums, raise_errors=raise_errors
            )
        return p_val
    if raise_errors:
        raise ValueError('Could not parse array \'{}\'.'.format(val))
    return None


def _parse_array_vals(
    indices, vals, rebase_arrays=True, vals_type=None, enums=None,
    raise_errors=True
):
    # Recursive parsing of multi-dimensional arrays of the type:
    # array2d(2..4, 1..3, [1, 2, 3, 4, 5, 6, 7, 8, 9])

    idx_set = indices[0]
    if len(indices) == 1:
        arr = {i: _parse_val(
            vals.pop(0), var_type=vals_type, enums=enums,
            raise_errors=raise_errors
        ) for i in idx_set}
    else:
        arr = {i: _parse_array_vals(
            indices[1:], vals, rebase_arrays=rebase_arrays, vals_type=vals_type,
            enums=enums, raise_errors=raise_errors
        ) for i in idx_set}

    if rebase_arrays and list(idx_set)[0] == 1:
        arr = rebase_array(arr)

    return arr


def _parse_indices(st, enums=None):
    # Parse indices of multi-dimensional arrays
    ss = st.strip().split(',')
    indices = []
    for s in ss:
        s = s.strip()
        cont_int_set_m = _cont_int_set_p.match(s)
        if cont_int_set_m:
            v1 = int(cont_int_set_m.group(1))
            v2 = int(cont_int_set_m.group(2))
            indices.append(range(v1, v2 + 1))
        elif _enum_val_p.match(s):
            if not enums or s not in enums:
                raise ValueError(
                    'No definition for enum type \'{}\' was provided.'.format(s)
                )
            # indices.append(range(1, len(enums[s]) + 1))
            indices.append(list(enums[s]))
        elif s == '{}':
            indices.append([])
        else:
            raise ValueError('Index \'{}\' is not well formatted.'.format(s))
    return indices


def parse_value(val, var_type=None, enums=None, rebase_arrays=True):

    if not var_type:
        p_val = _parse_array(
            val, rebase_arrays=rebase_arrays, enums=enums, raise_errors=False
        )
        if p_val is not None:
            return p_val
        return _parse_val(val, enums=enums)

    if 'dims' in var_type:
        return _parse_array(
            val, rebase_arrays=rebase_arrays, var_type=var_type, enums=enums
        )

    return _parse_val(val, var_type=var_type, enums=enums)


def dzn2dict(dzn, *, rebase_arrays=True, types=None):
    """Parses a dzn string or file into a dictionary of variable assignments.

    Parameters
    ----------
    dzn : str
        A dzn content string or a path to a dzn file.
    rebase_arrays : bool
        Whether to return arrays as zero-based lists or to return them as
        dictionaries, preserving the original index-sets.

    Returns
    -------
    dict
        A dictionary containing the variable assignments parsed from the
        input file or string.
    """
    dzn_ext = os.path.splitext(dzn)[1]
    if dzn_ext == '.dzn':
        with open(dzn) as f:
            dzn = f.read()

    enum_types = None
    if types:
        enum_types = []
        for var, var_type in types.items():
            if 'enum_type' in var_type and var_type['enum_type'] == var:
                enum_types.append(var)

    var_list = []
    dzn = _comm_p.sub('\n', dzn)
    stmts = _stmt_p.findall(dzn)
    for stmt in stmts:
        var_m = _var_p.match(stmt)
        if var_m:
            var = var_m.group('var')
            val = var_m.group('val')
            var_list.append((var, val))
        else:
            raise ValueError(
                'Unsupported parsing for statement:\n{}'.format(repr(stmt))
            )

    enums = None
    if enum_types:
        enums = {}
        remaining = []
        while len(var_list) > 0:
            var, val = var_list.pop(0)
            if var in enum_types:
                enum = None
                enum_m = _enum_p.match(val)
                if enum_m:
                    vals = enum_m.group('vals').strip()
                    if vals:
                        enum_vals = _parse_enum_vals(vals.split(','))
                        enum = IntEnum(
                            var, {v: i + 1 for i, v in enumerate(enum_vals)}
                        )
                if enum is None:
                    raise ValueError(
                        'Cannot parse enum type \'{} = {}\'.'.format(var, val)
                    )
                enums[var] = enum
            else:
                remaining.append((var, val))
        var_list = remaining

    assign = {}
    for var, val in var_list:
        var_type = None
        if types:
            var_type = types.get(var, None)
        assign[var] = parse_value(
            val, var_type=var_type, enums=enums, rebase_arrays=rebase_arrays
        )
    return assign

