from __future__ import print_function

# import
import os
import sys
import re
import logging
from functools import partial
import numpy as np
import pandas as pd

# functions
def df_rm_special_chars(df, colname):
    """Remove all special characters from column in pandas data.frame (in-place edit)
    """
    try:
        df[colname] = df[colname].astype(str).apply(lambda x: re.sub(r'[^A-Za-z0-9_ ]', '_', x))
    except TypeError:
        raise TypeError('Cannot remove special characters in column: {}'.format(colname))
    
def file_written(file_name):
    """Status on writing file
    file_name: string
    """
    print('File written: {}'.format(file_name), file=sys.stderr)


def make_range(x, set_zero_index=False):
    """Making a range from a string of comma-delimited and hyphenated number strings.
    If x = 'all', None returned
    x : string
    set_zero_index : change from 1-index to 0-index
    Example: 1,2,3,4
    Example: 1,2,5-6
    """
    x = str(x)
    if x.lower() == 'all':
        return None
    y = str(x).split(',')

    z = []
    for i in y:
        j = [int(x) for x in i.split('-')]
        if len(j) > 1:
            z = z + list(range(j[0], j[1]+1))
        else:
            z = z + j

    if set_zero_index:
        z = [x-1 for x in z]
        if min(z) < 0:
            raise ValueError('Negative values from setting zero index')

    return z


def check_gwl(gwl_file):
    """Checking that gwl in correct format
    gwl_file : input file name or file handle
    """
    # file read
    try:
        gwl_file = open(gwl_file, 'r')
    except ValueError:
        pass
    # checks
    for line in gwl_file:
        line = line.rstrip()
        if line is '':
            msg = 'Empty lines not allowed in gwl files'
            raise ValueError(msg)
        if not line[0] in ('A', 'D', 'R', 'W', 'F', 'C', 'B'):
            msg = '"{}" not a valid command ID'
            raise ValueError(msg.format(line[0]))
    # file close
    gwl_file.close()


def to_win(file_name, suffix='_win'):
    """Create a copy of a file but with windows line breakds
    file_name : str, name of file
    suffix : added to file name of copy
    Returns : name of new file
    """
    x = os.path.splitext(file_name)
    out_file = x[0] + suffix + x[1]
    with open(file_name) as inFH, open(out_file, 'w') as outFH:
        for line in inFH:
            line = line.replace('\n', '\r\n')
            outFH.write(line)
    return out_file


def backup_file(f):
    """
    Back up a file, old_file will be renamed to #old_file.n#, where n is a
    number incremented each time a backup takes place
    """
    if os.path.exists(f):
        dirname = os.path.dirname(f)
        basename = os.path.basename(f)
        count = 1
        rn_to = os.path.join(
            dirname, '#' + basename + '.{0}#'.format(count))
        while os.path.exists(rn_to):
            count += 1
            rn_to = os.path.join(
                dirname, '#' + basename + '.{0}#'.format(count))
        logging.info("Backing up {0} to {1}".format(f, rn_to))
        os.rename(f, rn_to)
        return rn_to
    else:
        logging.warning('{0} doesn\'t exist'.format(f))

        
def _reorder_384well(df, gwl, labware_type_col, position_col):
    odd_even = lambda x: (x % 2, x)

    # n-wells for labware type
    labware_type = df[labware_type_col].unique()[0]
    n_wells = gwl.db.get_labware_wells(labware_type)
    # sorting if 384 well
    if n_wells == 384:
        df = pd.concat([df.loc[df[position_col] % 2 != 0],
                        df.loc[df[position_col] % 2 == 0]])
    return df

    
def reorder_384well(df, gwl, labware_name_col, labware_type_col, position_col):
    """Reordering target positions of any 384-well labware types in df.
    Reordering to all odd-even in order to account for channel offset (reordering speeds up asp/disp)
    Method:
    # group by labware name and iter by groups
    ## if labware type is 384 well `n_wells = gwl.db.get_labware_wells(labware_type)`
    ### reorder by odd-even
    """
    f = partial(_reorder_384well, gwl=gwl,
                labware_type_col=labware_type_col,
                position_col=position_col)
    df = df.groupby([labware_name_col, labware_type_col]).apply(f).reset_index(drop=True)
    return df

    
# main
if __name__ == '__main__':
    pass
