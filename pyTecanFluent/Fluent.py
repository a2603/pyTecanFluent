from __future__ import print_function

# import
import os
import sys
import json
import pkg_resources
import numpy as np


#-- notes on gwl file format --#
# A;RackLabel;RackID;RackType;Position;TubeID;Volume;LiquidClass;Tip Type;TipMask;ForcedRackType
## 11 fields; 10 semicolons
# D;RackLabel;RackID;RackType;Position;TubeID;Volume;LiquidClass;Tip Type;TipMask;ForcedRackType
## 11 fields; 10 semicolons

def xstr(x):
    if x is None:
        return ''
    else:
        return x

def _psbl_liq_cls():
    """Returns a set of possible liquid classes available for Fluent
    """
    x = ('Water Free Multi', 'Water Free Multi No-cLLD',
         'Water Free Single', 'Water Free Single No-cLLD',
         'MasterMix Free Multi', 'MasterMix Free Multi No-cLLD',
         'MasterMix Free Single', 'MasterMix Free Single No-cLLD', 
         'Ethanol Free Multi',
         'Ethanol Free Single', 
         'DMSO Free Multi',
         'DMSO Free Single', 
         'Serum Free Multi',
         'Serum Free Single',
         'Water Contact Wet Multi', 'Water Contact Wet Multi No-cLLD',
         'Water Contact Wet Single', 'Water Contact Wet Single No-cLLD',
         'Water Mix', 'Water Mix No-cLLD')
    return x

class db():
    def __init__(self):
        d = os.path.split(__file__)[0]
        self.database_dir = os.path.join(d, 'database')
        # labware
        f = os.path.join(self.database_dir, 'labware.json')
        with open(f) as inF:
            self.labware = json.load(inF)
        # target position
        f = os.path.join(self.database_dir, 'target_position.json')
        with open(f) as inF:
            self.target_position = json.load(inF)
        # tip type
        f = os.path.join(self.database_dir, 'tip_type.json')
        with open(f) as inF:
            self.tip_type = json.load(inF)
        # liquid class
        f = os.path.join(self.database_dir, 'liquid_class.json')
        with open(f) as inF:
            self.liquid_class = json.load(inF)
        

            
class asp_disp():
    """Commands for aliquoting mastermix
    *Parameters*
    RackLabel
    RackID
    RackType
    Position
    TubeID
    Volume
    LiquidClass 
    TipType
    TipMask
    ForceRack
    MinDetected
    """

    def __init__(self, RackLabel, RackID, RackType,
                 Position, TubeID, Volume):
        self._ID = ''
        # aspirate parameters
        self.RackLabel = None
        self.RackID = None
        self.RackType = None
        self._Position = 1
        self.TubeID = None
        self.Volume = None
        self._LiquidClass = 'Water Free Single'
        self.TipType = None
        self.TipMask = None
        self.key_order = ['_ID',
                          'RackLabel', 'RackID', 'RackType',
                          'Position', 'TubeID', 'Volume',
                          'LiquidClass', 'TipType', 'TipMask']
        self.psbl_liq_cls = _psbl_liq_cls()

    def cmd(self):
        # list of values in correct order
        vals = [getattr(self, x) for x in self.key_order]
        # None to blank string
        vals = [xstr(x) for x in vals]
        # convert all to strings
        vals = [str(x) for x in vals]
        # return
        return ';'.join(vals)

    def liquid_classes(self):
        x = '\n,'.join(list(self.psbl_liq_cls))
        print(x)        

    @property
    def Position(self):
        return self._Position

    @Position.setter
    def Position(self, value):
        self._Position = int(value)

    @property
    def LiquidClass(self):
        return self._LiquidClass

    @LiquidClass.setter
    def LiquidClass(self, value):
        if value not in self.psbl_liq_cls:
            msg = 'Liquid class "{}" not allowed'
            raise TypeError(msg.format(value))
        self._LiquidClass = value
        

class aspirate(asp_disp):
    def __init__(self):
        asp_disp.__init__(self)
        self._ID = 'A'


class dispense(asp_disp):
    def __init__(self):
        asp_disp.__init__(self)
        self._ID = 'D'


class multi_disp():
    """Commands for aliquoting reagent to multiple labware positions
    *AspirateParameters*
    SrcRackLabel
    SrcRackID
    SrcRackType
    SrcPosition
    *DispenseParameters*
    DestRackLabel
    DestRackID
    DestRackType
    DestPosStart
    DestPosEnd
    *Samples*
    SampleCount
    *Other*
    Volume = How much volume per dispense?
    LiquidClass = Which liquid class to use? Default: 'Water Free Multi'
    NoOfMultiDisp = How many multi-dispenses?
    Labware_tracker = Labware object that tracks what labware is needed
    Returns
    * string of commands
    """

    def __init__(self, labware_tracker=None):
        self._ID = 'R'
        # aspirate parameters
        self.SrcRackLabel = None
        self.SrcRackID = None
        self.SrcRackType = None
        self.SrcPosition = 1
        # dispense parameters
        self.DestRackLabel = []
        self.DestRackID = []
        self.DestRackType = []
        self._DestPositions = [1]
        # other
        self.Volume = 1.0
        self.TipType = None
        self._LiquidClass = 'Water Free Multi'
        self.NoOfMultiDisp = 2
        self.psbl_liq_cls = _psbl_liq_cls()
        self.Labware_tracker = labware_tracker

    def xstr(self, x):
        if x is None:
            return ''
        else:
            return x

    def cmd(self):
        # volume as interable
        if hasattr(self.Volume, '__iter__'):
            self.Volumes = self.Volume
        else:
            self.Volumes = [self.Volume] * len(self.DestPositions)
                    
        # each multi-disp
        steps = []
        sample_cnt = 0
        while 1:
            # single-asp
            asp = aspirate()
            asp.RackLabel = self.SrcRackLabel
            asp.RackType = self.SrcRackType
            asp.Position = self.SrcPosition
            asp.LiquidClass = self.LiquidClass
            # determining total volume for this asp            
            dispenses_tmp = 0
            sample_cnt_tmp = sample_cnt
            total_asp_volume = 0
            while 1:
                sample_cnt_tmp += 1
                # Total samples reached
                if sample_cnt_tmp > len(self.DestPositions):
                    break
                # Number of multi-disp reached
                if dispenses_tmp >= self.NoOfMultiDisp:
                    sample_cnt_tmp -= 1 
                    break
                # Skipping 0-volumes
                if self.Volumes[sample_cnt_tmp-1] <= 0:
                    continue
                disp_volume = round(self.Volumes[sample_cnt_tmp-1], 2)
                if disp_volume > 0:
                    total_asp_volume += disp_volume
                    dispenses_tmp += 1
            # loading dispenses
            dispenses = []
            while 1:
                sample_cnt += 1
                # Total samples reached
                if sample_cnt > len(self.DestPositions):
                    break
                # Number of multi-disp reached
                if len(dispenses) >= self.NoOfMultiDisp:
                    sample_cnt -= 1 
                    break
                # Skipping 0-volumes
                if self.Volumes[sample_cnt-1] <= 0:
                    continue 
                disp = dispense()
                disp.RackLabel = self.DestRackLabel[sample_cnt-1]
                disp.RackType = self.DestRackType[sample_cnt-1]
                disp.Position = self.DestPositions[sample_cnt-1]
                disp.Volume = round(self.Volumes[sample_cnt-1], 2)
                disp.LiquidClass = self.LiquidClass
                if self.Labware_tracker is not None:
                    disp.TipType = self.Labware_tracker.tip_for_volume(total_asp_volume)
                if disp.Volume > 0:
                    dispenses.append(disp)
            # break if no more dispenses
            if len(dispenses) <= 0:
                break
            # adding asp-disp cycle
            asp.Volume = round(sum([x.Volume for x in dispenses]) * 1.05, 1)
            if self.Labware_tracker is not None:
                asp.TipType = self.Labware_tracker.tip_for_volume(total_asp_volume)
            steps.append(asp.cmd())
            steps = steps + [x.cmd() for x in dispenses]
            steps.append('W;')
            # labware tracking
            if self.Labware_tracker is not None:
                self.Labware_tracker.add(asp)
                self.Labware_tracker.add(disp, add_tip=False)
                
        # return string of commands
        return '\n'.join(steps)

    @property
    def LiquidClass(self):
        return self._LiquidClass

    @LiquidClass.setter
    def LiquidClass(self, value):
        if value not in self.psbl_liq_cls:
            msg = 'Liquid class "{}" not allowed'
            raise TypeError(msg.format(value))
        self._LiquidClass = value

    @property
    def DestPositions(self):
        return self._DestPositions

    @DestPositions.setter
    def DestPositions(self, values):
        try:
            values = values.tolist()
        except AttributeError:
            pass
        values = [int(x) for x in values]
        assert min(values) > 0, 'Min position is <= 0'
        self._DestPositions = values 

    @property
    def SampleCount(self):
        return len(self._DestPositions)

    
class reagent_distribution():
    """Commands for aliquoting mastermix
    *AspirateParameters*
    SrcRackLabel
    SrcRackID
    SrcRackType
    SrcPosStart
    SrcPosEnd
    *DispenseParameters*
    DestRackLabel
    DestRackID
    DestRackType
    DestPosStart
    DestPosEnd
    *Other*
    Volume = How much volume to asp/disp?
    LiquidClass = Which liquid class to use? Default: 'Water Free Multi'
    NoOfDiTiReuses = How many times to reuse tips?
    NoOfMultiDisp = How many multi-dispenses?
    Direction = Which way to pipette? Default:0
    ExcludedDestWell = Semi-colon separated string of locations to exclude

    *WashParameters*
    None?

    # Example: R;100ml_2;;Trough 100ml;1;1;96 Well Skirted PCR[003];;96 Well Skirted PCR;1;96;20;Water Free Multi;1;5;0
    """

    def __init__(self, ):
        self._ID = 'R'
        # aspirate parameters
        self.SrcRackLabel = None
        self.SrcRackID = None
        self.SrcRackType = None
        self.SrcPosStart = 1
        self.SrcPosEnd = 1
        # dispense parameters
        self.DestRackLabel = None
        self.DestRackID = None
        self.DestRackType = None
        self.DestPositions = 1
        self.DestPosEnd = 1
        # other
        self.Volume = 1
        self.LiquidClass = 'Water Free Multi'
        self.NoOfDiTiReuses = 1
        self.NoOfMultiDisp = 5
        self.Direction = 0
        self.ExcludedDestWell = None
        self.key_order = ['_ID',
                          'SrcRackLabel', 'SrcRackID', 'SrcRackType',
                          'SrcPosStart', 'SrcPosEnd',
                          'DestRackLabel', 'DestRackID', 'DestRackType',
                          'DestPosStart', 'DestPosEnd',
                          'Volume', 'LiquidClass', 'NoOfDiTiReuses',
                          'NoOfMultiDisp', 'Direction', 'ExcludedDestWell']

    def xstr(self, x):
        if x is None:
            return ''
        else:
            return x

    def cmd(self):
        # list of values in correct order
        vals = [getattr(self, x) for x in self.key_order]
        # None to blank string
        vals = [xstr(x) for x in vals]
        # convert all to strings
        vals = [str(x) for x in vals]
        # return
        return ';'.join(vals)



# main
if __name__ == '__main__':
    pass
