import json
import re
import sys
import traceback
from pprint import pprint

from PyPDF3.pdf import PageObject

from DataSheetParsers.DataSheet import DataSheet
from FeatureExtractors.MK_E_feature_extractor import MKFeatureListExtractor
from FeatureExtractors.feature_extractor import FeatureListExtractor
from DataSheetParsers.MK_E_DataSheet import MK_DataSheet
from TableExtractor import TableExtractor
from FeatureExtractors.feature_extractor import convert_type
from Utils import is_str, text2int, clean_line


class KLFeatureListExtractor(MKFeatureListExtractor):

    mcu_fields = re.compile(
        '(?P<q_status>[MP])(?P<s_fam>K)(?P<m_fam>L\d{2})(?P<key_attr>Z)(?P<flash>[\dM]+)(?P<si_rev>[A]?)(?P<temp_range>V)(?P<package>[a-zA-Z]+)(?P<cpu_frq>\d+)(?P<pack_type>[R]?)',
        re.IGNORECASE)

    def __init__(self, controller: str, datasheet: DataSheet, config):
        self.common_features = {}
        self.packages = {}
        super().__init__(controller, datasheet, config)

    def post_init(self):
        self.config_name = 'KL'
        self.mc_family = 'KL'



    def parse_code_name(self):  # UNIQUE FUNCTION FOR EVERY MCU FAMILY
        for mcu, features in self.features.items():
            mcus_fields = self.mcu_fields.match(mcu)
            qa_status, m_fam, s_fam_, key_attr, flash, si_rev, temp, package, cpu_frq, pack_type = mcus_fields.groups()
            pin_count, package = self.packages[package]
            features[package] = 1
            features['pin count'] = pin_count
            if 'M' in flash:
                flash = flash.split('M')[0]
                flash = int(flash) * 1024
            else:
                flash = int(flash)
            features['flash'] = flash
            features['CPU Frequency'] = flash

    # def extract_fields(self):
    #     fields = self.datasheet.table_of_content.get_node_by_name('Fields')
    #     tables = []
    #     if fields:
    #         t1 = self.extract_table(self.datasheet, page=self.datasheet.get_page_num(fields.page))
    #         if t1:
    #             tables.extend(t1)
    #         t2 = self.extract_table(self.datasheet, page=self.datasheet.get_page_num(fields.page) + 1)
    #         if t2:
    #             tables.extend(t2)

    def extract_features(self):
        controller_features = {}
        pages = [self.datasheet.pdf_file.getPage(0), self.datasheet.pdf_file.getPage(1)]
        or_page = self.datasheet.get_page_num(
            self.datasheet.table_of_content.get_node_by_name('Ordering information').page)
        ordering_tables = self.extract_table(self.datasheet, or_page)
        mcus = []
        for table in ordering_tables:
            if 'Ordering information' in table.get_cell(0, 0).text:
                mcus = list(map(lambda cell: cell.clean_text, table.get_col(0)[3:]))
            elif 'Product' in table.get_cell(0, 0).text:
                mcus = list(map(lambda cell: cell.clean_text, table.get_col(0)[2:]))
        for page in pages:
            text = page.extractText()
            for block in text.split("€"):
                if '°' in block or '•' in block:
                    block = block.replace('\n', ' ')
                    lines = block.split('°' if '°' in block else '•')
                    for line in lines:
                        line = clean_line(line)
                        line = text2int(line.lower())
                        if self.voltage_re.findall(line):
                            lo, hi = self.voltage_re.findall(line)[0]
                            self.create_new_or_merge('operating voltage', {'lo': float(lo), 'hi': float(hi)}, True)
                        if self.dma_re.findall(line):
                            channels = self.dma_re.findall(line)[0]
                            self.create_new_or_merge('DMA', {'channels': int(channels), 'count': 1}, True)
                        elif self.temperature_re.findall(line):
                            lo, hi = self.temperature_re.findall(line)[0]
                            lo, hi = map(lambda s: s.replace(' ', ''), (lo, hi))
                            self.create_new_or_merge('operating temperature', {'lo': float(lo), 'hi': float(hi)})
                        elif self.ram_re.findall(line):
                            ram, unit = self.ram_re.findall(line)[0]
                            ram = int(ram)
                            if unit.upper() == 'MB':
                                ram *= 1024
                            self.create_new_or_merge('SRAM', int(ram))
                        elif self.analog_cmp_re.findall(line):
                            count = self.analog_cmp_re.findall(line)[0]
                            if any(count):
                                count = int(count[0])
                            else:
                                count = 1
                            self.create_new_or_merge('timer', count)
                        elif self.timer_re.findall(line):
                            count = self.timer_re.findall(line)[0]
                            if count:
                                count = int(count[0])
                            else:
                                count = 1
                            self.create_new_or_merge('analog comparator', count)
                        elif self.adc_bits_re.findall(line):
                            bits = self.adc_bits_re.findall(line)[0]
                            count = self.adc_count_re.findall(line)
                            if not count:
                                count = 1
                            else:
                                count = int(count[0])
                            channels = self.adc_channels_re.findall(line)
                            if not channels:
                                channels = 0
                            else:
                                channels = int(channels[0])
                            if channels:
                                self.create_new_or_merge('ADC', {
                                    '{}-bit'.format(bits): {'count': count, 'channels': channels}})
                            else:
                                self.create_new_or_merge('ADC', {'{}-bit'.format(bits): {'count': count}})
                        if 'SPI' in line.upper():
                            if self.spi_re.findall(line):
                                count = self.spi_re.findall(line)[0]
                                self.create_new_or_merge('SPI', int(count))
                            else:
                                self.create_new_or_merge('SPI', 1)
                        if 'UART' in line.upper():
                            if self.uart_re.findall(line):
                                count = self.uart_re.findall(line)[0]
                                self.create_new_or_merge('uart', int(count))
                            else:
                                self.create_new_or_merge('uart', 1)
                        if 'I2C' in line.upper():
                            if self.i2c_re.findall(line):
                                count = self.i2c_re.findall(line)[0]
                                self.create_new_or_merge('I2C', int(count))
                            else:
                                self.create_new_or_merge('I2C', 1)
                        if 'LCD' in line:
                            self.create_new_or_merge('LCD', 1)

                        print(line, '\n')
                    print('=' * 20)
                    continue
                # print(block)
                # print('=' * 20)

        for mcu in mcus:
            if mcu:
                if not controller_features.get(mcu, False):
                    controller_features[mcu] = {}
                for common, value in self.common_features.items():
                    controller_features[mcu][common] = value

        return controller_features


if __name__ == '__main__':
    datasheet = MK_DataSheet(r"D:\PYTHON\py_pdf_stm\datasheets\KL\KL17P64M48SF2.pdf")
    with open('./../config.json') as fp:
        config = json.load(fp)
    feature_extractor = KLFeatureListExtractor('MKM', datasheet, config)
    feature_extractor.process()
    feature_extractor.unify_names()
    pprint(feature_extractor.features)