import copy
from collections import OrderedDict, defaultdict

from conan.tools.env.environment import ProfileEnvironment
from conans.model.conf import ConfDefinition
from conans.model.options import Options
from conans.model.recipe_ref import RecipeReference


class Profile(object):
    """A profile contains a set of setting (with values), environment variables
    """

    def __init__(self):
        # Input sections, as defined by user profile files and command line
        self.settings = OrderedDict()
        self.package_settings = defaultdict(OrderedDict)
        self.options = Options()
        self.tool_requires = OrderedDict()  # ref pattern: list of ref
        self.system_tools = []
        self.conf = ConfDefinition()
        self.buildenv = ProfileEnvironment()
        self.runenv = ProfileEnvironment()

        # Cached processed values
        self.processed_settings = None  # Settings with values, and smart completion
        self._package_settings_values = None

    def __repr__(self):
        return self.dumps()

    def serialize(self):
        # TODO: Remove it seems dead
        return {
            "settings": self.settings,
            "package_settings": self.package_settings,
            "options": self.options.serialize(),
            "tool_requires": self.tool_requires,
            "conf": self.conf.serialize(),
            # FIXME: Perform a serialize method for ProfileEnvironment
            "build_env": self.buildenv.dumps()
        }

    @property
    def package_settings_values(self):
        if self._package_settings_values is None:
            self._package_settings_values = {}
            for pkg, settings in self.package_settings.items():
                self._package_settings_values[pkg] = list(settings.items())
        return self._package_settings_values

    def process_settings(self, cache_settings):
        assert self.processed_settings is None, "processed settings must be None"
        self.processed_settings = cache_settings.copy()
        self.processed_settings.update_values(list(self.settings.items()))

    def dumps(self):
        result = ["[settings]"]
        for name, value in sorted(self.settings.items()):
            result.append("%s=%s" % (name, value))
        for package, values in self.package_settings.items():
            for name, value in sorted(values.items()):
                result.append("%s:%s=%s" % (package, name, value))

        options_str = self.options.dumps()
        if options_str:
            result.append("[options]")
            result.append(options_str)

        if self.tool_requires:
            result.append("[tool_requires]")
            for pattern, req_list in self.tool_requires.items():
                result.append("%s: %s" % (pattern, ", ".join(str(r) for r in req_list)))

        if self.system_tools:
            result.append("[system_tools]")
            result.extend(str(t) for t in self.system_tools)

        if self.conf:
            result.append("[conf]")
            result.append(self.conf.dumps())

        if self.buildenv:
            result.append("[buildenv]")
            result.append(self.buildenv.dumps())

        if self.runenv:
            result.append("[runenv]")
            result.append(self.runenv.dumps())

        if result and result[-1] != "":
            result.append("")

        return "\n".join(result).replace("\n\n", "\n")

    def compose_profile(self, other):
        self.update_settings(other.settings)
        self.update_package_settings(other.package_settings)
        self.options.update_options(other.options)
        # It is possible that build_requires are repeated, or same package but different versions
        for pattern, req_list in other.tool_requires.items():
            existing_build_requires = self.tool_requires.get(pattern)
            existing = OrderedDict()
            if existing_build_requires is not None:
                for br in existing_build_requires:
                    # TODO: Understand why sometimes they are str and other are RecipeReference
                    r = RecipeReference.loads(br) \
                         if not isinstance(br, RecipeReference) else br
                    existing[r.name] = br
            for req in req_list:
                r = RecipeReference.loads(req) \
                     if not isinstance(req, RecipeReference) else req
                existing[r.name] = req
            self.tool_requires[pattern] = list(existing.values())

        current_system_tools = {r.name: r for r in self.system_tools}
        current_system_tools.update({r.name: r for r in other.system_tools})
        self.system_tools = list(current_system_tools.values())
        self.conf.update_conf_definition(other.conf)
        self.buildenv.update_profile_env(other.buildenv)  # Profile composition, last has priority
        self.runenv.update_profile_env(other.runenv)

    def update_settings(self, new_settings):
        """Mix the specified settings with the current profile.
        Specified settings are prioritized to profile"""

        assert(isinstance(new_settings, OrderedDict))

        # apply the current profile
        res = copy.copy(self.settings)
        if new_settings:
            # Invalidate the current subsettings if the parent setting changes
            # Example: new_settings declare a different "compiler",
            # so invalidate the current "compiler.XXX"
            for name, value in new_settings.items():
                if "." not in name:
                    if name in self.settings and self.settings[name] != value:
                        for cur_name, _ in self.settings.items():
                            if cur_name.startswith("%s." % name):
                                del res[cur_name]
            # Now merge the new values
            res.update(new_settings)
            self.settings = res

    def update_package_settings(self, package_settings):
        """Mix the specified package settings with the specified profile.
        Specified package settings are prioritized to profile"""
        for package_name, settings in package_settings.items():
            self.package_settings[package_name].update(settings)
