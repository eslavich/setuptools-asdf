import os
import glob
from distutils import log
from setuptools.command.build_py import build_py
from setuptools import Command
import importlib.resources
from string import Template
import yaml
from urllib.request import pathname2url
import configparser


from . import resources


def find_files(path=""):
    log.warn("*** Entering find_files with path=%s", path)
    # schemas_dir = os.path.join(path, "schemas")
    # if os.path.exists(schemas_dir):
    #     result = glob.glob(os.path.join(schemas_dir, "**", "*.yaml"), recursive=True)
    # else:
    #     result = []
    # log.warn("*** Exiting find_files")
    # return result
    return []


def finalize_distribution_options(dist):
    log.warn("*** Entering finalize_distribution_options with dist=%s", dist)

    if os.path.exists("setup.cfg"):
        # TODO: do this in pyproject.toml?
        config = configparser.ConfigParser()
        config.read("setup.cfg")
        if (config.has_option("tool:setuptools_asdf", "enabled") and
            config.getboolean("tool:setuptools_asdf", "enabled")):
            dist.cmdclass["build_py"] = GenerateAsdfExtensionBuildPy
            dist.cmdclass["generate_asdf_extension"] = GenerateAsdfExtension

            if config.has_option("tool:setuptools_asdf", "schemas_root"):
                schemas_root = config.get("tool:setuptools_asdf", "schemas_root")
            else:
                schemas_root = "schemas"

            package = config.get("tool:setuptools_asdf", "package")
            package_root = os.path.join("src", package)
            os.makedirs(package_root, exist_ok=True)

            dist.packages = [package]
            dist.package_dir = { package: package_root }
            dist.package_data = {}

            for walk_result in os.walk(schemas_root):
                path = walk_result[0]
                schemas_package = ".".join([package, "schemas"] + path.split(os.sep)[1:])

                dist.packages.append(schemas_package)
                dist.package_dir[schemas_package] = path
                dist.package_data[schemas_package] = ["*.yaml"]


class GenerateAsdfExtension(Command):
    description = "TODO"

    def initialize_options(self):
        config = configparser.ConfigParser()
        config.read("setup.cfg")

        if config.has_option("tool:setuptools_asdf", "package"):
            self.package = config.get("tool:setuptools_asdf", "package")
        else:
            self.package = None

        if config.has_option("tool:setuptools_asdf", "schemas_root"):
            self.schemas_root = config.get("tool:setuptools_asdf", "schemas_root")
        else:
            self.schemas_root = "schemas"

        if config.has_option("tool:setuptools_asdf", "extension_module"):
            self.extension_module = config.get("tool:setuptools_asdf", "extension_module")
        else:
            self.extension_module = "extension"

    def finalize_options(self):
        if self.package is None:
            raise RuntimeError("Must specify 'package'")

        self.schemas_root = os.path.abspath(self.schemas_root)
        if not os.path.isdir(self.schemas_root):
            raise RuntimeError(f"schemas_root is not a directory: {self.schemas_path}")

    def run(self):
        build_py = self.get_finalized_command("build_py")
        package_root = os.path.abspath(build_py.get_package_dir(self.package))

        self._generate_extension_py(package_root)

    def _generate_extension_py(self, package_root):
        extension_class_name = "".join([w.capitalize() for w in self.package.split("_")] + ["Extension"])

        schema_id_to_relative_url = {}
        tag_to_schema_id = {}
        for path in glob.glob(os.path.join(self.schemas_root, "**", "*.yaml"), recursive=True):
            with open(path) as f:
                schema = yaml.safe_load(f.read())
            if "id" not in schema:
                raise RuntimeError(f"Schema at {path} missing 'id' property")
            schema_id = schema["id"]
            relative_path = os.path.relpath(path, self.schemas_root)
            relative_url = pathname2url(relative_path)
            schema_id_to_relative_url[schema_id] = relative_url
            if "tag" in schema:
                tag_to_schema_id[schema["tag"]] = schema_id

        sorted_keys = sorted(list(schema_id_to_relative_url.keys()))
        schema_id_to_relative_url_pairs = "\n".join(f'    "{k}": "{schema_id_to_relative_url[k]}",' for k in sorted_keys)

        sorted_keys = sorted(list(tag_to_schema_id.keys()))
        tag_to_schema_id_pairs = "\n".join(f'    "{k}": "{tag_to_schema_id[k]}",' for k in sorted_keys)

        develop_path_components = ", ".join([f'"{p}"' for p in os.path.relpath(self.schemas_root, package_root).split(os.sep)])

        template = Template(importlib.resources.read_text(resources, "extension.py.template"))

        content = template.substitute(
            extension_class_name=extension_class_name,
            schema_id_to_relative_url_pairs=schema_id_to_relative_url_pairs,
            tag_to_schema_id_pairs=tag_to_schema_id_pairs,
            package=self.package,
            develop_path_components=develop_path_components,
        )

        module_path = os.path.join(package_root, self.extension_module + ".py")
        with open(module_path, "w") as f:
            f.write(content)


class GenerateAsdfExtensionBuildPy(build_py):
    def run(self):
        generate_asdf_extension = self.get_finalized_command("generate_asdf_extension")
        generate_asdf_extension.run()

        super().run()
