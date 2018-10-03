import copy
import os
import sys
from typing import List

from DataSheetManager import DataSheetManager
from MKL_feature_extractor import MKLFeatureListExtractor
from MK_feature_extractor import MKFeatureListExtractor
from SMT32_feature_extractor import STM32FeatureListExtractor
import xlsxwriter


class FeatureManager:
    EXTRACTORS = {
        'STM32': STM32FeatureListExtractor,
        'MKL': MKLFeatureListExtractor,
        'MK': MKFeatureListExtractor,
    }

    def __init__(self, microcontrollers: List[str]):
        with open('config.json', 'r') as fp:
            if not fp.read():
                self.config = {'corrections': {}, 'unify': {}}
            else:
                fp.seek(0)
                self.config = json.load(fp)
        self.datasheet_manager = DataSheetManager(microcontrollers)
        self.mcs = microcontrollers
        self.mcs_features = {}
        self.same_features = []
        self.excel = xlsxwriter.Workbook('FeatureList.xlsx')
        self.sheet = self.excel.add_worksheet()

    def get_extractor(self,mc:str):
        for extractor_name in sorted(self.EXTRACTORS,key=lambda l:len(l),reverse=True):
            if extractor_name.upper() in mc.upper():
                return self.EXTRACTORS[extractor_name]


    def parse(self):
        self.datasheet_manager.get_or_download()
        for mc in self.mcs:
            extractor = self.get_extractor(mc)
            datasheet = self.datasheet_manager[mc]
            if datasheet:
                extractor_obj = extractor(mc, datasheet, self.config)
                extractor_obj.process()
                extractor_obj.unify_names()
                self.mcs_features[mc] = extractor_obj.features
                pass  # handle feature extraction
            else:
                raise Exception('Can\' find {} in database'.format(mc))

    def collect_same_features(self):
        same_features = set()
        for _, mcs in self.mcs_features.copy().items():
            for mc, features in mcs.items():
                if not same_features:
                    same_features = set(features.keys())
                    continue
                same_features.intersection_update(set(features.keys()))
        print(same_features)
        self.same_features = list(same_features)

    def write_excel_file(self):
        self.collect_same_features()

        # UTIL VARS
        merge_format = self.excel.add_format({'align': 'center', 'valign': 'center'})
        feature_vertical_offset = 0

        # Writing headers
        sheet = self.sheet
        sheet.write(0, 0, 'MCU family')
        sheet.write(1, 0, 'MCU')
        name_offset = 0
        sub_name_offset = 1
        mcs_features = copy.deepcopy(self.mcs_features)
        for n, (mc_name, sub_mcs) in enumerate(mcs_features.items()):
            sheet.merge_range(0, 1 + name_offset, 0, 1 + name_offset + len(sub_mcs) - 1, mc_name,
                              cell_format=merge_format)
            for sub_mc_name in sub_mcs.keys():
                sheet.write(1, sub_name_offset, sub_mc_name)
                sheet.set_column(sub_name_offset, sub_name_offset, width=len(sub_mc_name) + 3)
                sub_name_offset += 1
            name_offset += len(sub_mcs)
        feature_vertical_offset += 2

        # Writing common features
        mc_offset = 0
        sub_mc_offset = 0
        for n, common_feature in enumerate(self.same_features):
            sheet.write(feature_vertical_offset + n, 0, common_feature)
            mc_offset = 0
            for mc_name, sub_mcs in mcs_features.items():
                sub_mc_offset = 0
                for sub_mc_name, features in sub_mcs.items():
                    if common_feature not in features:
                        continue
                    feature = features.pop(common_feature)
                    if type(feature) == dict:
                        feature = r'/'.join(feature.keys())
                    if type(feature) == list:
                        feature = r'/'.join(feature)
                    sheet.write(n + feature_vertical_offset, 1 + sub_mc_offset + mc_offset, feature)
                    sub_mc_offset += 1
                mc_offset += len(sub_mcs)
        feature_vertical_offset += len(self.same_features)

        self.excel.close()


if __name__ == '__main__':
    import json

    if len(sys.argv) < 2:
        print('Usage: {} DATASHEET.pdj'.format(os.path.basename(sys.argv[0])))
        exit(0xDEADBEEF)
    controllers = sys.argv[1:]
    feature_manager = FeatureManager(controllers)
    feature_manager.parse()
    feature_manager.write_excel_file()
    with open('features.json', 'w') as fp:
        json.dump(feature_manager.mcs_features, fp, indent=2)
    # KL17P64M48SF6 stm32L451 MK11DN512AVMC5
    a = 5
