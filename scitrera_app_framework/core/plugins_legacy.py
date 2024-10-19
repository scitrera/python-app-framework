# from __future__ import annotations
#
# from queue import Queue
# from collections import OrderedDict
#
# from ..api import Plugin
#
#
# def order_plugins_by_dependencies(plugins: list[Plugin], existing_plugins: None | list[Plugin] = None, logger=None):
#     """
#     Old code adapted from rostra3 to manage dependency ordering for plugins.
#
#     TODO: review and simplify
#
#     :param plugins:
#     :param existing_plugins:
#     :param logger:
#     :return:
#     """
#     if plugins and not existing_plugins:
#         new_plugins = plugins
#         existing_plugins = []
#     elif plugins and existing_plugins:
#         # a bit ridiculous, but the idea is that we want to be sure we isolated the new ones...
#         # the definition of plugins while providing existing plugins is not well-defined,
#         # but presumably you'd expect it to be only the new plugins...
#         new_plugins = set(plugins).union(set(existing_plugins)) - set(existing_plugins)
#     else:
#         return existing_plugins or []  # this is the fallback if plugins resolves to False
#
#     remainder = set()
#     stack = Queue()  # type: Queue[Plugin]
#     for plugin in new_plugins:
#         stack.put(plugin)
#         remainder.add(plugin.get_name())
#
#     # note: this isn't efficient or pretty, but usually there won't be many plugins, so it's good enough...
#     result = OrderedDict((p.get_name(), p) for p in existing_plugins)
#     rejects = []
#     while not stack.empty():
#         plugin = stack.get()
#         dependencies = plugin.get_dependencies(v)
#         # note: these are key lookups! (don't forget that!)
#         if all(d in result for d in dependencies):  # easy case, all dependencies accounted for
#             result[plugin.get_name()] = plugin
#             remainder -= {plugin.get_name()}
#         elif all(d not in remainder for d in dependencies):  # worst case, will never succeed, just give in...
#             # TODO: maybe try to load/find plugins in the future? (hence duplication...)
#             # result[plugin.get_name()] = plugin
#             rejects.append(plugin)  # add to rejects list because we can't figure out the matches for dependencies
#             remainder -= {plugin.get_name()}
#             if logger:
#                 logger.warn('Skipping "%s" plugin because unable to resolve dependencies.', plugin.get_name())
#         else:
#             stack.put(plugin)  # put it back on the stack and wait...
#
#     return result.values(), rejects
