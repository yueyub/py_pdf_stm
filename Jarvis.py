import copy
import itertools
import json
import os
import sys
import traceback
from pathlib import Path
from random import randint,choice
from typing import Dict, Any

import xlsxwriter

from DataSheetManager import DataSheetManager
from FeaturesManager import FeatureManager
from FeatureExtractors.feature_extractor import convert_type
from PinManager import PinManager
from Utils import *


class MCUHelper:

    def __init__(self, feature_list: str) -> None:
        self.matching = {}  # type: Dict[str,Any]
        with open(feature_list) as fp:
            self.required_feature = json.load(fp)  # type: Dict[str,Any]
        controllers = sys.argv[2:]
        self.feature_manager = FeatureManager(controllers)
        self.mcu_features = self.feature_manager.mcs_features

    @staticmethod
    def match(required_value, feature_value, cmp_type, ):
        mismatch = False
        if cmp_type == '>':
            if not feature_value >= required_value:
                mismatch = True
        elif cmp_type == '<':
            if not feature_value <= required_value:
                mismatch = True
        elif cmp_type == '=':
            if not feature_value == required_value:
                mismatch = True
        else:
            if not feature_value >= required_value:
                mismatch = True
        return not mismatch

    @staticmethod
    def get_cmp_type(name):
        if name[-1] in '<>=':
            feature_name = name[:-1]
            cmp_type = name[-1]
        else:
            feature_name = name
            cmp_type = '>'
        return feature_name, cmp_type

    def compare(self, req_name, req_value, feature_name, feature_value):
        match = False
        req_name, cmp_type = self.get_cmp_type(req_name)
        if req_name != feature_name:
            if req_name != 'ANY':
                return False
        if is_dict(req_value) and is_dict(feature_value):
            for rk, rv in req_value.items():
                rk_name, _ = self.get_cmp_type(rk)
                for fk, fv in feature_value.items():
                    if rk_name !=fk:
                        continue
                    ret = self.compare(rk, rv, fk, fv)
                    if ret is not None:
                        if ret:
                            match = True
            return match
        elif is_float_or_int(req_value) and is_float_or_int(feature_value):
            return self.match(req_value, feature_value, cmp_type)
        elif is_str(req_value) and is_str(feature_value):
            print('STRINGS ARE NOT SUPPORTED YET')
            return False
        elif is_list(feature_value) and is_list(req_value):
            feature = set(feature_value)
            req = set(req_value)
            return any(feature.intersection(req))
        elif is_list(feature_value) and (is_str(req_value) or is_int(req_value)):
            return req_value in feature_value
        elif is_list(req_value) and (is_str(feature_value) or is_int(feature_value)):
            return feature_value in req_value
        print('WARNING: UNEXPECTED req_value or feature_value types!')
        print(req_value,feature_value)
        # raise NotImplementedError('UNEXPECTED req_value or feature_value types!')

    def collect_matching(self):
        self.print_user_req()
        print('Searching for matching microcontrolers!')
        for mcu_family, mcus in self.mcu_features.items():
            for mcu_name, mcu_features in mcus.items():
                matched = True
                for req_name, req_value in self.required_feature.items():
                    if not matched:
                        break
                    req_feature, cmp_type = self.get_cmp_type(req_name)
                    feature_value = mcu_features.get(req_feature.upper(), None)
                    if feature_value:
                        try:
                            matched &= self.compare(req_name, req_value, req_feature, feature_value)
                            # else:
                            #     matched &= self.match(req_value, feature_value, cmp_type)

                        except Exception as ex:
                            matched = False
                            print('ERROR:', ex)
                            print('INFO:', req_name, ':', req_value)
                            print('INFO2:', mcu_name, ':', feature_value)
                            traceback.print_exc()
                    else:
                        matched = False
                        break
                if matched:
                    self.matching[mcu_name] = mcu_features

        print('Found {} matching'.format(len(self.matching)))
        print('Matching microcontrolers:')
        if not self.matching:
            print('No matches')
        else:
            self.print_matching()

        return self

    def print_matching(self):
        for match_name, match_features in self.matching.items():
            print('\t', match_name)
            # for feature, value in match_features.items():
            #     print('\t', feature, ':', value)

    def print_user_req(self):
        print('Your requirements are:')
        for req_name, req_value in self.required_feature.items():
            if req_name[-1] in '<>=':
                cmp_type = req_name[-1]
                req_name = req_name[:-1]
            else:
                cmp_type = '>'
            print('\t', req_name, cmp_type, req_value)

    def get_common(self):
        same_features = set()
        for mc, features in self.matching.copy().items():
            if not same_features:
                same_features = set(features.keys())
                continue
            same_features.intersection_update(set(features.keys()))
        # print(same_features)
        return same_features

    def write_excel(self):
        same_features = self.get_common()
        excel = xlsxwriter.Workbook('Results.xlsx')
        sheet = excel.add_worksheet()

        middle = excel.add_format({'align': 'center', 'valign': 'center'})
        wraps = excel.add_format({'valign': 'top'})
        wraps.set_text_wrap()
        # Writing headers
        sheet.write(0, 0, 'MCU:')

        matching = copy.deepcopy(self.matching)
        for n, mc_name in enumerate(matching.keys()):
            sheet.write(0, 1 + n, mc_name, middle)
            sheet.set_column(0, 1 + n, width=len(mc_name) + 3)
        row_offset = 0
        for n, common_feature in enumerate(same_features):
            sheet.write(1 + n, 0, common_feature)
            for m, mc_features in enumerate(matching.values()):  # type: int,dict
                if mc_features.get(common_feature, False):
                    feature_value = mc_features.pop(common_feature)
                    if type(feature_value) is list:
                        feature_value = '/'.join(feature_value)
                    if type(feature_value) is dict:
                        feature_value = str(feature_value)
                    sheet.write(1 + n, 1 + m, feature_value)
                else:
                    sheet.write(1 + n, 1 + m, 'ERROR MISSING')
            row_offset = n + 1

        row_offset += 1
        sheet.write(row_offset, 0, 'OTHER')
        for m, mc_features in enumerate(matching.values()):  # type: int,dict
            row = ''
            count = 0
            row_offset_sub = 0
            for feature, value in mc_features.items():
                row += str(feature) + ' : ' + str(value) + '\n'
                count += 1
                if count > 10:
                    sheet.write(row_offset + row_offset_sub, 1 + m, row, wraps)
                    row_offset_sub = +1
                    count = 0
                    row = ''

        excel.close()


datasheets_path = Path('./datasheets/').absolute()


def parse_all():
    to_parse = []
    if datasheets_path.exists():
        for folder in datasheets_path.iterdir():
            if folder.is_dir():
                for ds in folder.iterdir():
                    if ds.is_file():
                        to_parse.append(ds.stem)
        FeatureManager(to_parse).parse()
    else:
        print('NO DATASHEETS FOUND')


def reunify_cache():
    feature_manager = FeatureManager([])
    feature_manager.load_cache()
    for mc_family_name, mc_family in feature_manager.mcs_features.items():
        unknown_names = []
        for mc, features in mc_family.items():

            # print(mc)
            mc_features = feature_manager.mcs_features[mc_family_name][mc].copy()
            config_name = feature_manager.get_config_name(mc)
            for feature_name, features_value in features.items():
                if features_value:
                    if config_name in feature_manager.config['unify']:
                        unify_list = feature_manager.config['unify'][config_name]
                        known = True
                        if feature_name not in unify_list:
                            if feature_name not in list(unify_list.values()):
                                known = False
                                if feature_name not in unknown_names:
                                    unknown_names.append(feature_name)
                        if known:
                            new_name = unify_list.get(feature_name, feature_name)  # in case name is already unified
                            values = mc_features.pop(feature_name)
                            new_name, values = convert_type(new_name, values)
                            mc_features[new_name] = values
                    else:
                        unknown_names.append(feature_name)

            feature_manager.mcs_features[mc_family_name][mc] = mc_features
        unknown_names = list(set(unknown_names))
        print('List of unknown features for', mc_family_name)
        print('Add correction if name is mangled')
        print('Or add unify for this feature')
        for unknown_feature in unknown_names:
            print('\t', unknown_feature)
        print('=' * 20)
    feature_manager.save()


def fit_pins(mcus, req_path):
    with open(req_path) as fp:
        reqs = json.load(fp)

    feature_manager = FeatureManager(mcus)
    for mcu in mcus:
        print('Fitting', mcu)
        fam = feature_manager.get_config_name(mcu)
        if fam in feature_manager.mcs_features:
            mcus = feature_manager.mcs_features[fam]
            for mcu_ in mcus:
                if mcu in mcu_:
                    mcu_data = mcus[mcu_]
                    if 'PINOUT' in mcu_data:
                        pin_manager = PinManager(mcu_data['PINOUT'], reqs)
                        pin_manager.read_pins()
                        pin_manager.fit_pins()
                        pin_manager.report()
                        pin_manager.serialize('./map.json')

                        exit()
                    else:
                        print(mcu, 'doesn\'t have pinout parsed/stored')
            else:
                print(mcu, 'not found in cache')
        else:
            print('Unknown MCU family:', fam)


def dump_unknown():
    feature_manager = FeatureManager([])
    config = feature_manager.config
    all_features = {}
    for mc_family, mcus in feature_manager.mcs_features.items():
        mc_family = feature_manager.get_config_name(mc_family)
        family_features = []
        for mc, features in mcus.items():
            family_features.extend(list(features.keys()))
        family_features = set(family_features)
        all_features[mc_family] = family_features
    unify = config['unify']
    with open('unknown.txt', 'w') as fp:
        for mc_family, features in all_features.items():
            fp.write(mc_family + ' \n')
            known = []
            known.extend(unify[mc_family].values())
            known.extend(unify[mc_family].keys())
            known = set(known)
            diffs = features.difference(known)
            for diff in diffs:
                fp.write('\t' + diff + '\n')


def chunkify(l,n):
    return [l[i:i + n] for i in range(0, len(l), n)]

def find():
    feature_manager = FeatureManager([])
    closest = []
    to_find = sys.argv[2]
    for _, mcus in feature_manager.mcs_features.items():
        for mcu in mcus.keys():
            match = 0
            for m_char, u_char in zip(mcu.upper(), to_find.upper()):
                if m_char == u_char:
                    match += 1
                elif m_char == 'X' or u_char == 'X':
                    match += 0.5
                elif u_char == '*':
                    match += 999
                else:
                    break

            if match > 2:
                closest.append((mcu,match))
    closest = list(sorted(closest,key = lambda val:val[1],reverse=True))
    print('40 closest MCUs to {}'.format(to_find))
    offset = 0
    while offset<len(closest):
        for line in chunkify(closest[offset:offset+40],5):
            for close,_ in line:
                print('\t',close,end='')
            print('\n')
        input('More?')
        offset+=40


def list_known():
    dump_mcu_name = "UNKNOWN"
    dump_all = False
    if len(sys.argv) < 2:
        print_usage()
    if sys.argv[2] == '*':
        dump_all = True
    else:
        dump_mcu_name = sys.argv[2].upper()
    feature_manager = FeatureManager([])
    config = feature_manager.config
    unify = config['unify']
    all_mcus = copy.deepcopy(list(feature_manager.mcs_features.values()))
    to_dump = []
    for mcus in all_mcus:
        for mcu, features in mcus.items():
            unifier = set(map(lambda s: s.upper(), unify.get(feature_manager.get_config_name(mcu),{}).values()))
            if dump_mcu_name in mcu.upper() or dump_all:

                feature_names = set(features.keys())
                unknown = feature_names.difference(unifier)
                for unk in unknown:
                    features.pop(unk)
                to_dump.append({mcu: features})

    with open('known_features.json', 'w') as fp:
        json.dump(to_dump, fp, indent=2)

    #

def func_help():
    func = sys.argv[2]
    to_parse = []
    if datasheets_path.exists():
        for folder in datasheets_path.iterdir():
            if folder.is_dir():
                for ds in folder.iterdir():
                    if ds.is_file():
                        to_parse.append(ds.stem)
    to_parse.append('STM32F217ZE')
    all_mcus = []
    feature_manager = FeatureManager([])
    for mcus in feature_manager.mcs_features.values():
        all_mcus.extend(mcus.keys())
    all_mcus.append('STM32F217Ix')
    random_datasheet = choice(to_parse)
    random_mcu = choice(all_mcus)
    if func == 'download':
        print('Example usage {} download {}'.format(sys.argv[0],random_datasheet))
        print('This will download and parse {}'.format(random_datasheet))
        print('It also can re-parse already existing datasheet or parse manually added one')

    elif func == 'filter':
        print('Example usage {} filter requirements.json'.format(sys.argv[0]))
        print('This will compare each of mcu in database to your requirements')
        print('Basic structure of "requirements.json" is:\n')

    elif func == 'fit-pins':
        print('Example usage {} fit-pins {} pin_config.json'.format(sys.argv[0],random_mcu))
        print('pin_config.json should have:')
        print('\tPACKAGE:string, key with package that you want you fit everything on')
        print('\tBLACK_LIST:array [OPTIONAL], black list of functions, if pin has this function, we won\'t use it')
        print('\tPINOUT:dictionary, is dictionary of modules, example:')
        print('\t  "OPTO":{ -- string, name of module')
        print('\t    "TYPE": "UART" -- string, module type')
        print('\t    "PINS": ["RX","TX"] -- array, pin sub-types')
        print('\t     OR')
        print('\t    "PINS": 5 -- int, number of pin used by this module, usefull for GPIO')

def print_usage():
    print('USAGE: {} [COMMAND]'.format(sys.argv[0]))
    print('\tdownload [MCU NAME HERE] - downloads and parses new datasheet')
    print('\tfilter [NAME.json]- filters MCUs by rules in NAME.json')
    print('\tfit-pins [MCU NAME HERE] [NAME.json]- tries to fit required pins into selected MCU')
    print('\tdump_cache - prints all MCUs in cache')
    print('\tre-unify - tries to re-unify everything')
    print('\tparse - re-parses all datasheets')
    print('\tshow - opens datasheet')
    print('\thelp [FUNCTION] - more information about function')
    print('\tfind [MCU NAME HERE] - finds closest name in database')
    print('\tdump_unknown - dumps all unknown features to file')
    print('\tdump_known [MCU NAME or *] - dumps all known controller\'s features, unknown won\'t be dumped')


if __name__ == '__main__':

    # if randint(0,5) == 2:  # Никаких обедов ёпт!
    #     print('Мужчина вы что не видите, у нас обед')
    #     exit()

    if len(sys.argv) > 1:
        if sys.argv[1] == 'parse':
            parse_all()
            exit(0xDEADBEEF)
        if sys.argv[1] == 'show':
            print(str(sys.argv[2:]))
            dsm = DataSheetManager(sys.argv[2:])
            for ds in dsm.iterate_paths():
                os.system(str(ds))
            exit(0xDEADBEEF)
        elif sys.argv[1] == 'download':
            feature_manager = FeatureManager(sys.argv[2:])
            feature_manager.parse()
            exit(0xDEADCAFE)
        elif sys.argv[1] == 're-unify':
            reunify_cache()
            exit(0xBEEFCAFE)
        elif sys.argv[1] == 'dump_cache':
            feature_manager = FeatureManager([])
            with open('./dump.txt', 'w') as fp:
                print('DUMPING ALL KNOWN MCU\'s')
                for family_name, family_mcus in feature_manager.mcs_features.items():
                    fp.write(family_name + ' :\n')
                    print(family_name, ':')
                    for mcu_name in family_mcus.keys():
                        fp.write('\t' + mcu_name + '\n')
                        print('\t', mcu_name)

        elif sys.argv[1] == 'filter':
            MCUHelper(sys.argv[2]).collect_matching().write_excel()
        elif sys.argv[1] == 'fit-pins':
            fit_pins(sys.argv[3:], sys.argv[2])
        elif sys.argv[1] == 'dump_unknown':
            dump_unknown()
        elif sys.argv[1] == 'dump_known':
            list_known()
        elif sys.argv[1] == 'find':
            find()
        elif sys.argv[1] == 'help':
            func_help()
        else:
            print_usage()
    else:
        print_usage()
