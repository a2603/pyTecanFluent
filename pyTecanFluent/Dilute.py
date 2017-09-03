from __future__ import print_function
# import
## batteries
import os
import sys
import argparse
import functools
from itertools import product
## 3rd party
import numpy as np
import pandas as pd
## package
from pyTecanFluent import Utils
from pyTecanFluent import Fluent
from pyTecanFluent import Labware

# functions
def get_desc():
    desc = 'Create robot commands for diluting samples'
    return desc

def parse_args(test_args=None, subparsers=None):
    # desc
    desc = get_desc()
    epi = """DESCRIPTION:
    Create a worklist file for the TECAN Fluent robot for diluting samples.
    The input is an Excel or tab-delimited file the following columns:
    * "TECAN_labware_name" = Any name you want to give to your plate of samples
    * "TECAN_labware_type" = The labware type matching your samples
    * "TECAN_target_position" = The location of your samples in your labware (plate)
    * "TECAN_sample_conc" = The sample concentrations (numeric value; units=ng/ul) 
    
    Notes:
    * You can designate the input table columns for each value (see options).
    * Sample locations in plates numbered are column-wise. 
    * All volumes are in ul.
    """
    if subparsers:
        parser = subparsers.add_parser('dilute', description=desc, epilog=epi,
                                       formatter_class=argparse.RawTextHelpFormatter)
    else:
        parser = argparse.ArgumentParser(description=desc, epilog=epi,
                                         formatter_class=argparse.RawTextHelpFormatter)

    # args
    ## I/O
    groupIO = parser.add_argument_group('I/O')
    groupIO.add_argument('concfile', metavar='ConcFile', type=str,
                         help='An excel or tab-delim file of concentrations')
    groupIO.add_argument('--prefix', type=str, default='TECAN_dilute',
                         help='Output file name prefix (default: %(default)s)')

    ## concentration file
    conc = parser.add_argument_group('Concentation file')
    conc.add_argument('--format', type=str, default=None,
                        help='File format (excel or tab). If not provided, the format is determined from the file extension') 
    conc.add_argument('--header', action='store_false', default=True,
                        help='Header in the file? (default: %(default)s)')
    conc.add_argument('--rows', type=str, default='all',
                      help='Which rows (not including header) of the column file to use ("all"=all rows; "1-48"=rows 1-48) (default: %(default)s)')

    ## dilution
    dil = parser.add_argument_group('Dilution')
    dil.add_argument('--dilution', type=float, default=5.0,
                     help='Target dilution concentration (ng/ul) (default: %(default)s)')
    dil.add_argument('--minvolume', type=float, default=2.0,
                     help='Minimum sample volume to use (default: %(default)s)')
    dil.add_argument('--maxvolume', type=float, default=30.0,
                     help='Maximum sample volume to use (default: %(default)s)')
    dil.add_argument('--mintotal', type=float, default=10.0,
                     help='Minimum post-dilution total volume (default: %(default)s)')
    dil.add_argument('--dlabware_name', type=str, default='100ml_1',
                     help='Name of labware containing the dilutant (default: %(default)s)')
    dil.add_argument('--dlabware_type', type=str, default='100ml_1',
                     choices=['100ml_1', '1.5ml Eppendorf',
                              '2.0ml Eppendorf', '96 Well Eppendorf TwinTec PCR'], 
                     help='Labware type containing the dilutant (default: %(default)s)')

    ## destination plate
    dest = parser.add_argument_group('Destination labware')
    dest.add_argument('--destname', type=str, default='Diluted DNA plate',
                      help='Destination labware name (default: %(default)s)')
    dest.add_argument('--desttype', type=str, default='96 Well Eppendorf TwinTec PCR',
                      choices=['96 Well Eppendorf TwinTec PCR', '384 Well Biorad PCR'],                          
                      help='Destination labware type  on TECAN worktable (default: %(default)s)')
    dest.add_argument('--deststart', type=int, default=1,
                      help='Starting location on the destination labware (default: %(default)s)')

    # parse & return
    if test_args:
        args = parser.parse_args(test_args)
        return args

    return parser


def main(args=None):
    # Input
    if args is None:
        args = parse_args()
    check_args(args)
    
    # Import
    df_conc = conc2df(args.concfile, 
                      file_format=args.format,
                      row_select=args.rows, 
                      header=args.header)
    
    # Determining dilution volumes
    df_conc = dilution_volumes(df_conc, 
                               dilute_conc=args.dilution,
                               min_vol=args.minvolume,
                               max_vol=args.maxvolume,
                               min_total=args.mintotal,
                               dest_type=args.desttype)
    
    # Adding destination data
    df_conc = add_dest(df_conc,
                       dest_name=args.destname,
                       dest_type=args.desttype,
                       dest_start=args.deststart)

    
    # Reordering dest if plate type is 384-well
    try:
        n_wells = Labware.LABWARE_DB[args.desttype]['wells']
    except KeyError:
        msg = 'Labware type "{}" does not have "wells" attribute'
        raise KeyError(msg.format(args.desttype))
    if n_wells == '384':
        df_conc = reorder_384well(df_conc, 'TECAN_dest_target_position')

    # Writing out gwl file
    lw_tracker = Labware.labware_tracker()
    gwl_file = args.prefix + '.gwl'
    with open(gwl_file, 'w') as gwlFH:
        ## Dilutant
        pip_dilutant(df_conc, outFH=gwlFH,
                     src_labware_name=args.dlabware_name,
                     src_labware_type=args.dlabware_type,
                     lw_tracker=lw_tracker)
        ## Sample
        pip_samples(df_conc, outFH=gwlFH,
                    lw_tracker=lw_tracker)

    # making labware table
    df_labware = lw_tracker.labware_table()
    lw_file = args.prefix + '_labware.txt'
    df_labware.to_csv(lw_file, sep='\t', index=False)

    # Writing out table
    conc_file = args.prefix + '_conc.txt'
    df_conc.round(1).to_csv(conc_file, sep='\t', index=False)

    # Create windows-line breaks formatted versions
    gwl_file_win = Utils.to_win(gwl_file)
    conc_file_win = Utils.to_win(conc_file)
    lw_file_win = Utils.to_win(lw_file)

    # status
    Utils.file_written(gwl_file)
    Utils.file_written(conc_file)
    Utils.file_written(lw_file)
    Utils.file_written(gwl_file_win)
    Utils.file_written(conc_file_win)    
    Utils.file_written(lw_file_win)

    
    # end
    return (gwl_file, gwl_file_win, conc_file, conc_file_win)


def check_args(args):
    """Checking user input
    """
    # input table column IDs
    args.rows = Utils.make_range(args.rows, set_zero_index=True)
    # dilution
    assert args.dilution >= 0.0, '--dilution must be >= 0'
    assert args.minvolume >= 0.0, '--minvolume must be >= 0'
    assert args.maxvolume > 0.0, '--maxvolume must be > 0'
    # destination labware type
    try:
        Labware.LABWARE_DB[args.desttype]
    except KeyError:
        msg = 'Destination labware type "{}" not recognized'

        raise ValueError(msg.format(args.desttype))

                         
def conc2df(concfile, row_select=None, file_format=None, header=True):
    """Loading a concentration file as a pandas dataframe
    """
    if header==True:
        header=0
    else:
        header=None
    # format
    if file_format is None:
        if concfile.endswith('.csv'):
            file_format = 'csv'
        elif concfile.endswith('.txt'):
            file_format = 'tab'
        elif concfile.endswith('.xls') or concfile.endswith('.xlsx'):
            file_format = 'excel'
    else:
        file_format = file_format.lower()
        
    # load via pandas IO
    if file_format == 'csv':
        df = pd.read_csv(concfile, sep=',', header=header)        
    elif file_format == 'tab':
        df = pd.read_csv(concfile, sep='\t', header=header)
    elif file_format == 'excel':
        xls = pd.ExcelFile(concfile)
        df = pd.read_excel(xls, header=header)
    else:
        raise ValueError('Concentration file not in usable format')

    # checking file format
    check_df_conc(df)

    # return
    return df

def missing_cols(df, req_cols):
    msg = 'Required column "{}" not found'
    for req_col in req_cols:
        if req_col not in df.columns.values:
            raise ValueError(msg.format(req_col))    

def check_df_conc(df_conc):
    """Assertions of df_conc object formatting
    """
    # checking for columns
    req_cols = ['TECAN_labware_name', 'TECAN_labware_type',
                'TECAN_target_position', 'TECAN_sample_conc']
    missing_cols(df_conc, req_cols)

    # checking labware types
    msg = 'ERROR (concfile, line={}): labware type not recognized: {}'
    for i,lt in enumerate(df_conc['TECAN_labware_type']):
        try:
            Labware.LABWARE_DB[lt]
        except KeyError:
            raise KeyError(msg.format(i, lt))
                         
    # checking sample locations (>=1)
    msg = 'ERROR (concfile, line={}): location is < 1'
    for i,loc in enumerate(df_conc['TECAN_target_position']):
        if loc < 1:
            print(msg.format(i), file=sys.stderr)
    
    # checking sample conc
    msg = 'WARNING (concfile, line={}): concentration is <= 0'
    for i,sc in enumerate(df_conc['TECAN_sample_conc']):
        if sc <= 0.0:
            print(msg.format(i), file=sys.stderr)

    # adding target position
    df_conc['TECAN_target_location'] = df_conc.apply(add_target_location, axis=1)


def add_target_location(row):
    labware_type = row['TECAN_labware_type']
    try:
        tp = Labware.LABWARE_DB[labware_type]
    except KeyError:
        msg = 'Labware type "{}" not recognized'
        raise KeyError(msg.format(labware_type))
    try:
        tp = Labware.LABWARE_DB[labware_type]['target_location']
    except KeyError:
        msg = 'Labware type "{}" does not have target location key'
        raise KeyError(msg.format(labware_type))
    return tp
            
def calc_sample_volume(row, dilute_conc, min_vol, max_vol):
    """sample_volume = dilute_conc * total_volume / conc 
    (v1 = c2*v2/c1)
    If sample_volume > max possibl volume to use, then just use max
    """
    # use all if very low conc
    if row['TECAN_sample_conc'] <= 0:
        return max_vol
    # calc volume to use
    x = dilute_conc * row['TECAN_total_volume'] / row['TECAN_sample_conc']
    # ceiling
    if x > max_vol:
        x = max_vol
    # floor
    if x < min_vol:
        x = min_vol
    return x

def calc_dilutant_volume(row):
    """ dilutatant volume = total_volume - sample_volume
    """
    x = row['TECAN_total_volume'] - row['TECAN_sample_volume']
    if x < 0:
        x = 0
    return x

def calc_total_volume(row, min_vol, max_vol, dilute_conc):
    """Calculating post-dlution volume
    """
    x = row['TECAN_sample_conc'] * min_vol / dilute_conc
    if x > max_vol:
        x = max_vol
    return x    

def dilution_volumes(df_conc, dilute_conc, min_vol, max_vol, 
                     min_total, dest_type):
    """Setting the amoutn of sample to aliquot for dilution
    df_conc: pd.dataframe
    dilute_conc: concentration to dilute to 
    min_vol: min volume of sample to use
    max_vol: max total volume to use
    min_total: minimum total post-dilution volume
    dest_type: labware type for destination labware
    """
    # c1*v1 = c2*v2 
    # v2 = c1 * v1 / c2
    # v1 = c2 * v2 / c1

    # max well volume
    try:
        Labware.LABWARE_DB[dest_type]
    except KeyError:
        msg = 'Destination labware type "{}" not recognized'
        raise ValueError(msg.format(dest_type))
    try:
        max_well_vol = Labware.LABWARE_DB[dest_type]['max_volume']
    except KeyError:
        msg = 'Cannot find max_volume for labware type: {}'
        raise ValueError(msg.format(dest_type))

    # converting all negative concentrations to zero
    f = lambda row: 0 if row['TECAN_sample_conc'] < 0 else row['TECAN_sample_conc']
    df_conc['TECAN_sample_conc'] = df_conc.apply(f, axis=1)
    
    # range of dilutions
    samp_vol_range = max_vol - min_vol
    target_total_vol = round(samp_vol_range / 2 + min_vol)
    
    # final volume
    f = functools.partial(calc_total_volume, dilute_conc=dilute_conc,
                          min_vol=min_vol, max_vol=max_vol)
    df_conc['TECAN_total_volume'] = df_conc.apply(f, axis=1)
    if max(df_conc['TECAN_total_volume']) > max_well_vol:
        msg = 'ERROR: post-dilution volume exceeds max possible well volume.'
        msg += ' Lower --minvolume or chane destination labware type.'
        raise ValueError(msg)
    
    # raising total post-dilute volume if too low of dilute volume (if small dilution factor)
    df_conc.loc[df_conc.TECAN_total_volume < min_total, 'TECAN_total_volume'] = min_total
    # setting volumes
    f = functools.partial(calc_sample_volume, dilute_conc=dilute_conc,
                          min_vol=min_vol, max_vol=max_vol)
    df_conc['TECAN_sample_volume'] = df_conc.apply(f, axis=1)
    # dilutatant volume = total_volume - sample_volume
    df_conc['TECAN_dilutant_volume'] = df_conc.apply(calc_dilutant_volume, axis=1)
    # updating total volume
    f = lambda row: row['TECAN_sample_volume'] + row['TECAN_dilutant_volume']
    df_conc['TECAN_total_volume'] = df_conc.apply(f, axis=1)
    # calculating final conc
    f = lambda row: row['TECAN_sample_conc'] * row['TECAN_sample_volume'] / row['TECAN_total_volume']
    df_conc['TECAN_final_conc'] = df_conc.apply(f, axis=1)
    ## target conc hit?
    msg_low = 'WARNING: (concfile, line{}): final concentration is low: {}'
    msg_high = 'WARNING: (concfile, line{}): final concentration is high: {}'
    for i,fc in enumerate(df_conc['TECAN_final_conc']):
        fc = round(fc, 1)
        if fc < round(dilute_conc, 1):            
            print(msg_low.format(i, fc), file=sys.stderr)
        if fc > round(dilute_conc, 1):
            print(msg_high.format(i, fc), file=sys.stderr)
        
    # return
    return df_conc
        

def add_dest(df_conc, dest_name, dest_type, dest_start=1):
    """Setting destination locations for samples & primers.
    Adding to df_conc:
      [dest_labware, dest_location]
    """
    dest_start= int(dest_start)
    
    # adding columns
    df_conc['TECAN_dest_labware_name'] = dest_name
    df_conc['TECAN_dest_labware_type'] = dest_type
    df_conc['TECAN_dest_target_location'] = Labware.LABWARE_DB[dest_type]['target_location']
    df_conc['TECAN_dest_target_position'] = list(range(dest_start, dest_start + df_conc.shape[0]))

    # return
    return df_conc


def reorder_384well(df, reorder_col):
    """Reorder values so that the odd, then the even locations are
    transferred. This is faster for a 384-well plate
    df: pandas.DataFrame
    reorder_col: column name to reorder
    """
    df['TECAN_sort_IS_EVEN'] = [x % 2 == 0 for x in df[reorder_col]]
    df.sort_values(by=['TECAN_sort_IS_EVEN', reorder_col], inplace=True)
    df = df.drop('TECAN_sort_IS_EVEN', 1)
    df.index = range(df.shape[0])
    return df


def pip_dilutant(df_conc, outFH, src_labware_name, 
                 src_labware_type=None, lw_tracker=None):
    """Writing worklist commands for aliquoting dilutant.
    Using 1-asp-multi-disp with 200 ul tips.
    Method:
    * calc max multi-dispense for 50 or 200 ul tips 
    """
    # determing how many multi-disp per tip
    max_vol = max(df_conc.TECAN_dilutant_volume)
    if max_vol > 900:
        raise ValueError('Max dilutant volume >900ul')
    if max_vol * 2 < 45:
        n_disp= int(np.floor(45 / max_vol))   # using 50 ul tips
    elif max_vol * 2 < 180:
        n_disp = int(np.floor(180 / max_vol))  # using 200 ul tips
    else:
        n_disp = int(np.floor(900 / max_vol))  # using 1000 ul tips
        
    # making multi-disp object
    outFH.write('C;Dilutant\n')
    MD = Fluent.multi_disp()
    MD.SrcRackLabel = src_labware_name
    MD.SrcRackType = src_labware_type
    MD.SrcPosition = 1                                   # need to set for all channels?
    MD.DestRackLabel = df_conc.TECAN_dest_labware_name
    MD.DestRackType = df_conc.TECAN_dest_labware_type
    MD.DestPositions = df_conc.TECAN_dest_target_position
    MD.Volume = df_conc.TECAN_dilutant_volume             
    MD.NoOfMultiDisp = n_disp
    MD.Labware_tracker = lw_tracker
    # writing
    outFH.write(MD.cmd() + '\n')

    
def pip_samples(df_conc, outFH, lw_tracker=None):
    """Commands for aliquoting samples into dilutant
    """
    outFH.write('C;Samples\n')
    # for each Sample-PCR_rxn_rep, write out asp/dispense commands
    for i in range(df_conc.shape[0]):
        # aspiration
        asp = Fluent.aspirate()
        asp.RackLabel = df_conc.ix[i,'TECAN_labware_name']
        asp.RackType = df_conc.ix[i,'TECAN_labware_type']
        asp.Position = df_conc.ix[i,'TECAN_target_position']
        asp.Volume = round(df_conc.ix[i,'TECAN_sample_volume'], 2)
        asp.LiquidClass = 'Water Contact Wet Single No-cLLD'
        outFH.write(asp.cmd() + '\n')
        
        # dispensing
        disp = Fluent.dispense()
        disp.RackLabel = df_conc.ix[i,'TECAN_dest_labware_name']
        disp.RackType = df_conc.ix[i,'TECAN_dest_labware_type']        
        disp.Position = df_conc.ix[i,'TECAN_dest_target_position']
        disp.Volume = round(df_conc.ix[i,'TECAN_sample_volume'], 2)
        disp.LiquidClass = 'Water Contact Wet Single No-cLLD'
        outFH.write(disp.cmd() + '\n')

        # tip to waste
        outFH.write('W;\n')
        lw_tracker.add(asp)
        lw_tracker.add(disp, add_tip=False)

# main
if __name__ == '__main__':
    pass


