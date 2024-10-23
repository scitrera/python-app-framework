from __future__ import annotations

from logging import Logger

from scitrera_app_framework import (init_framework, register_plugin, get_extensions)
from scitrera_app_framework.api import Plugin
from scitrera_app_framework.api.variables2 import Variables2 as Variables

ext_name = 'multi-test'


class MultiPluginTest1(Plugin):
    NAME = 'Test1'

    def name(self) -> str:
        return self.NAME

    def extension_point_name(self, v: Variables) -> str:
        return ext_name

    def is_enabled(self, v: Variables) -> bool:
        return False

    def is_multi_extension(self, v: Variables) -> bool:
        return True

    def initialize(self, v: Variables, logger: Logger) -> object | None:
        return 'Test1-Item'


class MultiPluginTest2(Plugin):
    NAME = 'Test2'

    def name(self) -> str:
        return self.NAME

    def extension_point_name(self, v: Variables) -> str:
        return ext_name

    def is_enabled(self, v: Variables) -> bool:
        return False

    def is_multi_extension(self, v: Variables) -> bool:
        return True

    def initialize(self, v: Variables, logger: Logger) -> object | None:
        return 'Test2-Item'


if __name__ == '__main__':
    init_framework('test-app-q3')
    register_plugin(MultiPluginTest1)
    register_plugin(MultiPluginTest2)

    hits = get_extensions(ext_name)
    print(hits)
