from .planning import protected


def _execute(runner, argv: list[str]) -> None:
    if hasattr(runner, "interactive"):
        runner.interactive(argv)
    else:
        runner.run(argv)


def install_missing(plan: dict, runner) -> None:
    for package in plan["packages_install"]:
        _execute(runner, ["omarchy", "pkg", "add", package])
    for name, version in plan["mise_install"].items():
        _execute(runner, ["mise", "use", "--global", "--pin", name + "@" + version])
    for spec in plan["uv_install"].values():
        _execute(runner, ["uv", "tool", "install", "--force", spec])


def remove_extras(plan: dict, runner) -> None:
    for name in plan["uv_remove"]:
        _execute(runner, ["uv", "tool", "uninstall", name])
    for name in plan["mise_remove"]:
        _execute(runner, ["mise", "unuse", "--global", name])
    for package in plan["packages_remove"]:
        output = runner.run(["pacman", "-Rns", "--print", "--print-format", "%n", package])
        removed = set(output.splitlines())
        if package not in removed or any(protected(name) or name in plan["desired_packages"] for name in removed):
            raise ValueError("package removal preflight changed: " + package)
        _execute(runner, ["omarchy", "pkg", "drop", package])
