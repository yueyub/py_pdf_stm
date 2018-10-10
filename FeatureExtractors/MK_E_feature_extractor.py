import json
import re
import sys
import traceback
from pprint import pprint

from PyPDF3.pdf import PageObject

from DataSheetParsers.DataSheet import DataSheet
from FeatureExtractors.feature_extractor import FeatureListExtractor
from DataSheetParsers.MK_E_DataSheet import MK_DataSheet
from TableExtractor import TableExtractor
from FeatureExtractors.feature_extractor import convert_type
from Utils import is_str, text2int, clean_line


class MKFeatureListExtractor(FeatureListExtractor):
    voltage_re = re.compile('Voltage\srange:\s*(?P<lo>[\d.]+)\s?V?\sto\s(?P<hi>[\d.]+)\sV?',
                            re.IGNORECASE)

    temperature_re = re.compile('Temp.*:\s*(?P<lo>[-–+]?\s?[\d]+).?C?\sto\s(?P<hi>[-+]?\s?[\d]+).?C?',
                                re.IGNORECASE)

    ram_re = re.compile('(?P<ram>\d+)\s(?P<unit>\w+)\s.*\sRAM', re.IGNORECASE)

    adc_count_re = re.compile('^(?P<count>\d+)x?\s', re.IGNORECASE)

    adc_bits_re = re.compile('(?P<bits>\d+)-bit\s.*\sADC\s',
                             re.IGNORECASE)

    adc_channels_re = re.compile('(?P<channels>\d+)\schannels\s',
                                 re.IGNORECASE)

    spi_re = re.compile('(?P<count>[\d]+)-?x?.*SPI.*',
                        re.IGNORECASE)
    analog_cmp_re = re.compile('(?P<count>(\d+)?).*analog.comparator.?\s',
                        re.IGNORECASE)
    timer_re = re.compile('(?P<count>\d+)?(?!\s?channel|.{1,2}-?bit).*Timer.*',
                        re.IGNORECASE)

    i2c_re = re.compile('(?P<count>[\d]+)-?x?.*I2C.*',
                        re.IGNORECASE)
    uart_re = re.compile('(?P<count>\d+)?.*UART.*',
                        re.IGNORECASE)
    dma_re = re.compile('(?P<channels>\d+)?.*DMA.*',
                        re.IGNORECASE)

    package_re = re.compile(
        '^.?\s?(?P<package_short>[\d\w]+)\s=\s(?P<pin_count>\d+)\s(?P<package_full>[\d\w]+)\s\(.*\)',
        re.IGNORECASE | re.MULTILINE)
    mcu_fields = re.compile(
        '(?P<q_status>[MP])(?P<m_fam>[K])(?P<s_fam>M1|M3)(?P<adc>[\d])(?P<key_attr>Z)(?P<flash>[\dM]+)(?P<si_rev>[ZA]?)(?P<temp_range>C)(?P<package>[a-zA-Z]+)(?P<cpu_frq>\d?)(?P<pack_type>[R]?)',
        re.IGNORECASE)
    freq_re = re.compile('^.?\s?(?P<key>[\d\w]+)\s=\s(?P<freq>[\d]+)\s(?P<units>[MHGz]{3})',
                            re.IGNORECASE | re.MULTILINE)
    temp_re = re.compile('^.?\s?(?P<key>[\d\w]+)\s=\s(?P<lo>[-–+\d]+)\sto\s(?P<hi>[-–+\d]+)',
                            re.IGNORECASE | re.MULTILINE)

    mcu_names = re.compile('([MP][K](M1|M3)[\d]Z[\dM]+[ZA]?C[a-zA-Z]+\d?[R]?)', re.IGNORECASE)

    def __init__(self, controller: str, datasheet: DataSheet, config):
        self.common_features = {}
        self.packages = {}
        self.freqs = {}
        self.temperatures = {}
        super().__init__(controller, datasheet, config)

    def post_init(self):
        self.config_name = 'MK'
        self.mc_family = 'MK'

    def process(self):
        # self.extract_fields()
        self.extract_fields()
        self.features = self.extract_features()
        self.parse_code_name()
        return self.features

    def parse_code_name(self):  # UNIQUE FUNCTION FOR EVERY MCU FAMILY
        for mcu, features in self.features.items():
            mcus_fields = self.mcu_fields.match(mcu).groups()
            # print(mcus_fields)
            qa_status, m_fam, s_fam, _, key_attr, flash, si_rev, temp, package, cpu_frq, pack_type = mcus_fields
            pin_count, package = self.packages[package]
            features[package] = 1
            features['pin count'] = pin_count
            if 'M' in flash:
                flash = flash.split('M')[0]
                flash = int(flash) * 1024
            else:
                flash = int(flash)
            features['flash'] = flash
            features['CPU Frequency'] = self.freqs[cpu_frq][0]
            features['operating temperature'] = {'lo':self.temperatures[cpu_frq][0],'hi':self.temperatures[cpu_frq][1]}

    def extract_fields(self):
        fields = self.datasheet.table_of_content.get_node_by_name('Fields')
        text = ''
        if fields:
            text += self.datasheet.pdf_file.getPage(self.datasheet.get_page_num(fields.page)).extractText()
            text += self.datasheet.pdf_file.getPage(self.datasheet.get_page_num(fields.page) + 1).extractText()
        if self.package_re.findall(text):
            for package_info in self.package_re.findall(text):
                short_name, pin_count, full_name = package_info
                self.packages[short_name] = (pin_count, full_name)
        if self.freq_re.findall(text):
            for freq in self.freq_re.findall(text):
                key, freq, units = freq
                self.freqs[key] = (int(freq), units)
        if self.temp_re.findall(text):
            for freq in self.temp_re.findall(text):
                key, lo, hi = freq
                self.temperatures[key] = (int(lo),int(hi))

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
        mcus = []
        for page in pages:
            text = page.extractText()
            for block in text.split("€"):
                if 'Supports the following' in block:
                    mcus = [m[0] for m in self.mcu_names.findall(block)]
                    # print(mcus)
                    continue
                if '°' in block:
                    block = block.replace('\n', ' ')
                    lines = block.split('°')
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
                            if count:
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
                            self.create_new_or_merge('LCD',1)

                        # print(line, '\n')
                    # print('=' * 20)
                    continue
                # print(block)
                # print('=' * 20)

        for mcu in mcus:
            if not controller_features.get(mcu, False):
                controller_features[mcu] = {}
            for common, value in self.common_features.items():
                controller_features[mcu][common] = value

        return controller_features

    def create_new_or_merge(self, key, value, override=False):
        if not override:
            if key in self.common_features:
                value = self.merge_features(self.common_features[key], value)
        self.common_features[key] = value


if __name__ == '__main__':
    datasheet = MK_DataSheet(r"D:\PYTHON\py_pdf_stm\datasheets\MK\MKMxxZxxACxx5.pdf")
    with open('./../config.json') as fp:
        config = json.load(fp)
    feature_extractor = MKFeatureListExtractor('MKM', datasheet, config)
    feature_extractor.process()
    feature_extractor.unify_names()
    pprint(feature_extractor.features)
