# Changelog

Commands and Undo/Redo system.

## [1.4.5] - 2022-10-06
# Fixed
- Don't assume that get_history_item() always returns a valid entry.

## [1.4.4] - 2022-08-30
### Added
- Support for specifying optional and required keyword arguments when registering commands from C++

## [1.4.3] - 2022-08-23
### Changed
- Removed check for kwargs default.

## [1.4.2] - 2022-08-02
### Fixed
- Ensure GIL when calling back into python functions.

## [1.4.1] - 2022-06-16
### Fixed
- Command groups now fire events to callbacks registered using 'omni.kit.undo.subscribe_on_change'.

## [1.4.0] - 2022-06-02
### Added
- Support for repeating the last command that was executed or redone.

## [1.3.1] - 2022-06-01
### Added
- Support for specifying default keyword arguments to C++ commands.

## [1.3.0] - 2022-05-26
### Added
- C++ support for registering, deregistering, executing, and undoing/redoing commands.
- Support for preventing groups of commands from being added to the undo stack.

## [1.2.2] - 2022-05-05
### Changed
- Use relative import to avoid exposing _call_callbacks() to users.

## [1.2.1] - 2022-04-20
### Fixed
- Callbacks now fire on redo.
- Callbacks now fire within the command's undo block.

## [1.2.0] - 2022-02-10
### Added
- Support for pre- and post-do callbacks

## [1.1.0] - 2021-12-30
### Added
- added @abstractmethod to 'do()' method

## [1.0.0] - 2019-06-18
### Added
- Initial Commands System
