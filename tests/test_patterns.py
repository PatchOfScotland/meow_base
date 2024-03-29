"""
Tests for all pattern and monitor creation and operations.

Author(s): David Marchant, Nikolaj Ingemann Gade
"""

import io
import os
import socket
import tempfile
import unittest

from multiprocessing import Pipe
from time import sleep, time
from watchdog.events import FileSystemEvent

from ..meow_base.core.vars import FILE_CREATE_EVENT, EVENT_TYPE, \
    EVENT_RULE, EVENT_PATH, SWEEP_START, \
    SWEEP_JUMP, SWEEP_STOP, DIR_EVENTS
from ..meow_base.functionality.file_io import make_dir
from ..meow_base.functionality.meow import create_rule, assemble_patterns_dict, \
    assemble_recipes_dict
from ..meow_base.patterns.file_event_pattern import FileEventPattern, \
    WatchdogMonitor, WatchdogEventHandler, _DEFAULT_MASK, WATCHDOG_HASH, \
    WATCHDOG_BASE, EVENT_TYPE_WATCHDOG, WATCHDOG_EVENT_KEYS, \
    create_watchdog_event
from ..meow_base.patterns.socket_event_pattern import SocketPattern, \
    SocketMonitor, create_socket_file_event
from ..meow_base.recipes.jupyter_notebook_recipe import JupyterNotebookRecipe
from ..meow_base.recipes.python_recipe import PythonRecipe
from .shared import SharedTestPattern, SharedTestRecipe, \
    BAREBONES_NOTEBOOK, TEST_MONITOR_BASE, COUNTING_PYTHON_SCRIPT, \
    APPENDING_NOTEBOOK, setup, teardown, check_port_in_use, \
    check_shutdown_port_in_timeout


TEST_PORT = 8080

def patterns_equal(tester, pattern_one, pattern_two):
    tester.assertEqual(pattern_one.name, pattern_two.name)
    tester.assertEqual(pattern_one.recipe, pattern_two.recipe)
    tester.assertEqual(pattern_one.parameters, pattern_two.parameters)
    tester.assertEqual(pattern_one.outputs, pattern_two.outputs)
    tester.assertEqual(pattern_one.sweep, pattern_two.sweep)

    if type(pattern_one) != type(pattern_two):
        raise TypeError("Expected matching pattern types. Got "
                        f"{type(pattern_one)} and {type(pattern_two)}")
    
    if type(pattern_one) == FileEventPattern:
        tester.assertEqual(pattern_one.triggering_path, 
            pattern_two.triggering_path)
        tester.assertEqual(pattern_one.triggering_file, 
            pattern_two.triggering_file)
        tester.assertEqual(pattern_one.event_mask, pattern_two.event_mask)
    elif type(pattern_one) == SocketPattern:
        tester.assertEqual(pattern_one.triggering_port, 
            pattern_two.triggering_port)
    else:
        raise TypeError(f"Unknown pattern type {type(pattern_one)}")

def recipes_equal(tester, recipe_one, recipe_two):
    tester.assertEqual(recipe_one.name, recipe_two.name)
    tester.assertEqual(recipe_one.recipe, recipe_two.recipe)
    tester.assertEqual(recipe_one.parameters, recipe_two.parameters)
    tester.assertEqual(recipe_one.requirements, recipe_two.requirements)
    tester.assertEqual(recipe_one.source, recipe_two.source)

class FileEventPatternTests(unittest.TestCase):
    def setUp(self)->None:
        super().setUp()
        setup()

    def tearDown(self)->None:
        super().tearDown()
        teardown()

    # Test FileEventPattern created
    def testFileEventPatternCreationMinimum(self)->None:
        FileEventPattern("name", "path", "recipe", "file")

    # Test FileEventPattern not created with empty name
    def testFileEventPatternCreationEmptyName(self)->None:
        with self.assertRaises(ValueError):
            FileEventPattern("", "path", "recipe", "file")

    # Test FileEventPattern not created with empty path
    def testFileEventPatternCreationEmptyPath(self)->None:
        with self.assertRaises(ValueError):
            FileEventPattern("name", "", "recipe", "file")

    # Test FileEventPattern not created with empty recipe
    def testFileEventPatternCreationEmptyRecipe(self)->None:
        with self.assertRaises(ValueError):
            FileEventPattern("name", "path", "", "file")

    # Test FileEventPattern not created with empty file
    def testFileEventPatternCreationEmptyFile(self)->None:
        with self.assertRaises(ValueError):
            FileEventPattern("name", "path", "recipe", "")

    # Test FileEventPattern not created with invalid name
    def testFileEventPatternCreationInvalidName(self)->None:
        with self.assertRaises(ValueError):
            FileEventPattern("@name", "path", "recipe", "file")

    # Test FileEventPattern not created with invalid recipe
    def testFileEventPatternCreationInvalidRecipe(self)->None:
        with self.assertRaises(ValueError):
            FileEventPattern("name", "path", "@recipe", "file")

    # Test FileEventPattern not created with invalid file
    def testFileEventPatternCreationInvalidFile(self)->None:
        with self.assertRaises(ValueError):
            FileEventPattern("name", "path", "recipe", "@file")

    # Test FileEventPattern created with valid name
    def testFileEventPatternSetupName(self)->None:
        name = "name"
        fep = FileEventPattern(name, "path", "recipe", "file")
        self.assertEqual(fep.name, name)

    # Test FileEventPattern created with valid path
    def testFileEventPatternSetupPath(self)->None:
        path = "path"
        fep = FileEventPattern("name", path, "recipe", "file")
        self.assertEqual(fep.triggering_path, path)

    # Test FileEventPattern created with valid recipe
    def testFileEventPatternSetupRecipe(self)->None:
        recipe = "recipe"
        fep = FileEventPattern("name", "path", recipe, "file")
        self.assertEqual(fep.recipe, recipe)

    # Test FileEventPattern created with valid file
    def testFileEventPatternSetupFile(self)->None:
        file = "file"
        fep = FileEventPattern("name", "path", "recipe", file)
        self.assertEqual(fep.triggering_file, file)

    # Test FileEventPattern created with valid parameters
    def testFileEventPatternSetupParementers(self)->None:
        parameters = {
            "a": 1,
            "b": True
        }
        fep = FileEventPattern(
            "name", "path", "recipe", "file", parameters=parameters)
        self.assertEqual(fep.parameters, parameters)

    # Test FileEventPattern created with valid outputs
    def testFileEventPatternSetupOutputs(self)->None:
        outputs = {
            "a": "a",
            "b": "b"
        }
        fep = FileEventPattern(
            "name", "path", "recipe", "file", outputs=outputs)
        self.assertEqual(fep.outputs, outputs)

    # Test FileEventPattern created with valid event mask
    def testFileEventPatternEventMask(self)->None:
        fep = FileEventPattern("name", "path", "recipe", "file")
        self.assertEqual(fep.event_mask, _DEFAULT_MASK)

        with self.assertRaises(TypeError):
            fep = FileEventPattern("name", "path", "recipe", "file", 
                event_mask=FILE_CREATE_EVENT)

        with self.assertRaises(ValueError):
            fep = FileEventPattern("name", "path", "recipe", "file", 
                event_mask=["nope"])

        with self.assertRaises(ValueError):
            fep = FileEventPattern("name", "path", "recipe", "file", 
                event_mask=[FILE_CREATE_EVENT, "nope"])

    # Test FileEventPattern created with valid parameter sweep
    def testFileEventPatternSweep(self)->None:
        sweeps = {
            'first':{
                SWEEP_START: 0,
                SWEEP_STOP: 3,
                SWEEP_JUMP: 1
            },
            'second':{
                SWEEP_START: 10,
                SWEEP_STOP: 0,
                SWEEP_JUMP: -2
            }
        }
        fep = FileEventPattern("name", "path", "recipe", "file", sweep=sweeps)
        self.assertEqual(fep.sweep, sweeps)

        bad_sweep = {
            'first':{
                SWEEP_START: 0,
                SWEEP_STOP: 3,
                SWEEP_JUMP: -1
            },
        }
        with self.assertRaises(ValueError):
            fep = FileEventPattern("name", "path", "recipe", "file", 
                sweep=bad_sweep)

        bad_sweep = {
            'second':{
                SWEEP_START: 10,
                SWEEP_STOP: 0,
                SWEEP_JUMP: 1
            }
        }
        with self.assertRaises(ValueError):
            fep = FileEventPattern("name", "path", "recipe", "file", 
                sweep=bad_sweep)

class WatchdogMonitorTests(unittest.TestCase):
    def setUp(self)->None:
        super().setUp()
        setup()

    def tearDown(self)->None:
        super().tearDown()
        teardown()

    # Test creation of watchdog event dict
    def testCreateWatchdogEvent(self)->None:
        pattern = FileEventPattern(
            "pattern", 
            "file_path", 
            "recipe_one", 
            "infile", 
            parameters={
                "extra":"A line from a test Pattern",
                "outfile":"result_path"
            })
        recipe = JupyterNotebookRecipe(
            "recipe_one", APPENDING_NOTEBOOK)

        rule = create_rule(pattern, recipe)

        with self.assertRaises(TypeError):
            event = create_watchdog_event("path", rule)

        event = create_watchdog_event(
            "path", rule, "base", time(), "hash")

        self.assertEqual(type(event), dict)
        self.assertEqual(len(event.keys()), len(WATCHDOG_EVENT_KEYS))
        for key, value in WATCHDOG_EVENT_KEYS.items():
            self.assertTrue(key in event.keys())
            self.assertIsInstance(event[key], value)
        self.assertEqual(event[EVENT_TYPE], EVENT_TYPE_WATCHDOG)
        self.assertEqual(event[EVENT_PATH], "path")
        self.assertEqual(event[EVENT_RULE], rule)
        self.assertEqual(event[WATCHDOG_BASE], "base")
        self.assertEqual(event[WATCHDOG_HASH], "hash")

        event = create_watchdog_event(
            "path2", 
            rule, 
            "base", 
            time(), 
            "hash", 
            extras={"a":1}
        )

        self.assertEqual(type(event), dict)
        self.assertTrue(EVENT_TYPE in event.keys())
        self.assertTrue(EVENT_PATH in event.keys())
        self.assertTrue(EVENT_RULE in event.keys())
        self.assertTrue(WATCHDOG_BASE in event.keys())
        self.assertTrue(WATCHDOG_HASH in event.keys())
        self.assertEqual(len(event.keys()), len(WATCHDOG_EVENT_KEYS)+1)
        for key, value in WATCHDOG_EVENT_KEYS.items():
            self.assertTrue(key in event.keys())
            self.assertIsInstance(event[key], value)
        self.assertEqual(event[EVENT_TYPE], EVENT_TYPE_WATCHDOG)
        self.assertEqual(event[EVENT_PATH], "path2")
        self.assertEqual(event[EVENT_RULE], rule)
        self.assertEqual(event["a"], 1)
        self.assertEqual(event[WATCHDOG_BASE], "base")
        self.assertEqual(event[WATCHDOG_HASH], "hash")

    #TODO test valid watchdog event

    # Test WatchdogMonitor created 
    def testWatchdogMonitorMinimum(self)->None:
        from_monitor = Pipe()
        WatchdogMonitor(TEST_MONITOR_BASE, {}, {}, from_monitor[1])

    # Test WatchdogMonitor naming
    def testWatchdogMonitorNaming(self)->None:
        test_name = "test_name"
        monitor = WatchdogMonitor(TEST_MONITOR_BASE, {}, {}, name=test_name)
        self.assertEqual(monitor.name, test_name)

        monitor = WatchdogMonitor(TEST_MONITOR_BASE, {}, {})
        self.assertTrue(monitor.name.startswith("monitor_"))

    # Test WatchdogMonitor identifies expected events in base directory
    def testWatchdogMonitorEventIdentificaion(self)->None:
        from_monitor_reader, from_monitor_writer = Pipe()

        pattern_one = FileEventPattern(
            "pattern_one", "A", "recipe_one", "file_one")
        recipe = JupyterNotebookRecipe(
            "recipe_one", BAREBONES_NOTEBOOK)

        patterns = {
            pattern_one.name: pattern_one,
        }
        recipes = {
            recipe.name: recipe,
        }

        wm = WatchdogMonitor(TEST_MONITOR_BASE, patterns, recipes)
        wm.to_runner_event = from_monitor_writer

        rules = wm.get_rules()

        self.assertEqual(len(rules), 1)
        rule = rules[list(rules.keys())[0]]
        
        wm.start()

        open(os.path.join(TEST_MONITOR_BASE, "A"), "w")
        if from_monitor_reader.poll(3):
            message = from_monitor_reader.recv()

        self.assertIsNotNone(message)
        event = message
        self.assertIsNotNone(event)
        self.assertEqual(type(event), dict)
        self.assertTrue(EVENT_TYPE in event.keys())        
        self.assertTrue(EVENT_PATH in event.keys())        
        self.assertTrue(WATCHDOG_BASE in event.keys())        
        self.assertTrue(EVENT_RULE in event.keys())        
        self.assertEqual(event[EVENT_TYPE], EVENT_TYPE_WATCHDOG)
        self.assertEqual(event[EVENT_PATH], 
            os.path.join(TEST_MONITOR_BASE, "A"))
        self.assertEqual(event[WATCHDOG_BASE], TEST_MONITOR_BASE)
        self.assertEqual(event[EVENT_RULE].name, rule.name)

        open(os.path.join(TEST_MONITOR_BASE, "B"), "w")
        if from_monitor_reader.poll(3):
            new_message = from_monitor_reader.recv()
        else:
            new_message = None
        self.assertIsNone(new_message)

        wm.stop()

    # Test WatchdogMonitor identifies expected events in sub directories
    def testMonitoring(self)->None:
        pattern_one = FileEventPattern(
            "pattern_one", 
            os.path.join("start", "A.txt"), 
            "recipe_one", 
            "infile", 
            parameters={})
        recipe = JupyterNotebookRecipe(
            "recipe_one", BAREBONES_NOTEBOOK)

        patterns = {
            pattern_one.name: pattern_one,
        }
        recipes = {
            recipe.name: recipe,
        }

        wm = WatchdogMonitor(
            TEST_MONITOR_BASE,
            patterns,
            recipes,
        )

        rules = wm.get_rules()
        rule = rules[list(rules.keys())[0]]

        from_monitor_reader, from_monitor_writer = Pipe()
        wm.to_runner_event = from_monitor_writer
   
        wm.start()

        start_dir = os.path.join(TEST_MONITOR_BASE, "start")
        make_dir(start_dir)
        self.assertTrue(start_dir)
        with open(os.path.join(start_dir, "A.txt"), "w") as f:
            f.write("Initial Data")

        self.assertTrue(os.path.exists(os.path.join(start_dir, "A.txt")))

        messages = []
        while True:
            if from_monitor_reader.poll(3):
                messages.append(from_monitor_reader.recv())
            else:
                break
        self.assertTrue(len(messages), 1)
        message = messages[0]

        self.assertEqual(type(message), dict)
        self.assertIn(EVENT_TYPE, message)
        self.assertEqual(message[EVENT_TYPE], EVENT_TYPE_WATCHDOG)
        self.assertIn(WATCHDOG_BASE, message)
        self.assertEqual(message[WATCHDOG_BASE], TEST_MONITOR_BASE)
        self.assertIn(EVENT_PATH, message)
        self.assertEqual(message[EVENT_PATH], 
            os.path.join(start_dir, "A.txt"))
        self.assertIn(EVENT_RULE, message)
        self.assertEqual(message[EVENT_RULE].name, rule.name)

        wm.stop()

    # Test WatchdogMonitor identifies directory content updates
    def testMonitorDirectoryMonitoring(self)->None:
        pattern_one = FileEventPattern(
            "pattern_one", 
            os.path.join("top"), 
            "recipe_one", 
            "dir_to_count", 
            parameters={},
            event_mask=DIR_EVENTS
        )
        recipe = PythonRecipe(
            "recipe_one", COUNTING_PYTHON_SCRIPT)

        patterns = {
            pattern_one.name: pattern_one,
        }
        recipes = {
            recipe.name: recipe,
        }

        wm = WatchdogMonitor(
            TEST_MONITOR_BASE,
            patterns,
            recipes,
            settletime=3
        )

        rules = wm.get_rules()
        rule = rules[list(rules.keys())[0]]

        from_monitor_reader, from_monitor_writer = Pipe()
        wm.to_runner_event = from_monitor_writer
   
        wm.start()

        start_dir = os.path.join(TEST_MONITOR_BASE, "top")

        contents = 10
        make_dir(start_dir)
        for i in range(contents):
            with open(os.path.join(start_dir, f"{i}.txt"), "w") as f:
                f.write("-")
            sleep(1)

        self.assertTrue(start_dir)
        for i in range(contents):
            self.assertTrue(os.path.exists(
                os.path.join(start_dir, f"{i}.txt"))
            )

        messages = []
        while True:
            if from_monitor_reader.poll(5):
                messages.append(from_monitor_reader.recv())
            else:
                break
        self.assertTrue(len(messages), 1)
        message = messages[0]

        self.assertEqual(type(message), dict)
        self.assertIn(EVENT_TYPE, message)
        self.assertEqual(message[EVENT_TYPE], EVENT_TYPE_WATCHDOG)
        self.assertIn(WATCHDOG_BASE, message)
        self.assertEqual(message[WATCHDOG_BASE], TEST_MONITOR_BASE)
        self.assertIn(EVENT_PATH, message)
        self.assertEqual(message[EVENT_PATH], start_dir)
        self.assertIn(EVENT_RULE, message)
        self.assertEqual(message[EVENT_RULE].name, rule.name)

        wm.stop()

    # Test WatchdogMonitor identifies fake events for retroactive patterns
    def testMonitoringRetroActive(self)->None:
        pattern_one = FileEventPattern(
            "pattern_one", 
            os.path.join("start", "A.txt"), 
            "recipe_one", 
            "infile", 
            parameters={})
        recipe = JupyterNotebookRecipe(
            "recipe_one", BAREBONES_NOTEBOOK)

        patterns = {
            pattern_one.name: pattern_one,
        }
        recipes = {
            recipe.name: recipe,
        }

        start_dir = os.path.join(TEST_MONITOR_BASE, "start")
        make_dir(start_dir)
        self.assertTrue(start_dir)
        with open(os.path.join(start_dir, "A.txt"), "w") as f:
            f.write("Initial Data")

        self.assertTrue(os.path.exists(os.path.join(start_dir, "A.txt")))

        monitor_debug_stream = io.StringIO("")

        wm = WatchdogMonitor(
            TEST_MONITOR_BASE,
            patterns,
            recipes,
            print=monitor_debug_stream,
            logging=3, 
            settletime=1
        )

        rules = wm.get_rules()
        rule = rules[list(rules.keys())[0]]

        from_monitor_reader, from_monitor_writer = Pipe()
        wm.to_runner_event = from_monitor_writer
   
        wm.start()

        messages = []
        while True:
            if from_monitor_reader.poll(3):
                messages.append(from_monitor_reader.recv())
            else:
                break
        self.assertTrue(len(messages), 1)
        message = messages[0]

        self.assertEqual(type(message), dict)
        self.assertIn(EVENT_TYPE, message)
        self.assertEqual(message[EVENT_TYPE], EVENT_TYPE_WATCHDOG)
        self.assertIn(WATCHDOG_BASE, message)
        self.assertEqual(message[WATCHDOG_BASE], TEST_MONITOR_BASE)
        self.assertIn(EVENT_PATH, message)
        self.assertEqual(message[EVENT_PATH], 
            os.path.join(start_dir, "A.txt"))
        self.assertIn(EVENT_RULE, message)
        self.assertEqual(message[EVENT_RULE].name, rule.name)

        wm.stop()

    # Test WatchdogMonitor identifies events for retroacive directory patterns
    def testMonitorRetroActiveDirectory(self)->None:
        contents = 10
        start_dir = os.path.join(TEST_MONITOR_BASE, "top")
        make_dir(start_dir)
        for i in range(contents):
            with open(os.path.join(start_dir, f"{i}.txt"), "w") as f:
                f.write("-")
            sleep(1)

        self.assertTrue(start_dir)
        for i in range(contents):
            self.assertTrue(os.path.exists(
                os.path.join(start_dir, f"{i}.txt"))
            )

        pattern_one = FileEventPattern(
            "pattern_one", 
            os.path.join("top"), 
            "recipe_one", 
            "dir_to_count", 
            parameters={},
            event_mask=DIR_EVENTS
        )
        recipe = PythonRecipe(
            "recipe_one", COUNTING_PYTHON_SCRIPT)

        patterns = {
            pattern_one.name: pattern_one,
        }
        recipes = {
            recipe.name: recipe,
        }

        wm = WatchdogMonitor(
            TEST_MONITOR_BASE,
            patterns,
            recipes,
            settletime=3
        )

        rules = wm.get_rules()
        rule = rules[list(rules.keys())[0]]

        from_monitor_reader, from_monitor_writer = Pipe()
        wm.to_runner_event = from_monitor_writer
   
        wm.start()

        messages = []
        while True:
            if from_monitor_reader.poll(5):
                messages.append(from_monitor_reader.recv())
            else:
                break
        self.assertTrue(len(messages), 1)
        message = messages[0]

        self.assertEqual(type(message), dict)
        self.assertIn(EVENT_TYPE, message)
        self.assertEqual(message[EVENT_TYPE], EVENT_TYPE_WATCHDOG)
        self.assertIn(WATCHDOG_BASE, message)
        self.assertEqual(message[WATCHDOG_BASE], TEST_MONITOR_BASE)
        self.assertIn(EVENT_PATH, message)
        self.assertEqual(message[EVENT_PATH], start_dir)
        self.assertIn(EVENT_RULE, message)
        self.assertEqual(message[EVENT_RULE].name, rule.name)

        wm.stop()

    # Test WatchdogMonitor identifies events for retroacive directory patterns
    def testMonitorRetroAndOngoingDirectory(self)->None:
        start_dir = os.path.join(TEST_MONITOR_BASE, "dir")
        make_dir(start_dir)

        make_dir(os.path.join(start_dir, "A"))

        pattern_one = FileEventPattern(
            "pattern_one", 
            os.path.join("dir", "*"), 
            "recipe_one", 
            "dir_to_count", 
            parameters={},
            event_mask=DIR_EVENTS
        )
        recipe = PythonRecipe(
            "recipe_one", COUNTING_PYTHON_SCRIPT)

        patterns = {
            pattern_one.name: pattern_one,
        }
        recipes = {
            recipe.name: recipe,
        }

        wm = WatchdogMonitor(
            TEST_MONITOR_BASE,
            patterns,
            recipes,
            settletime=3
        )

        rules = wm.get_rules()
        rule = rules[list(rules.keys())[0]]

        from_monitor_reader, from_monitor_writer = Pipe()
        wm.to_runner_event = from_monitor_writer
   
        wm.start()

        messages = []
        while True:
            if from_monitor_reader.poll(5):
                messages.append(from_monitor_reader.recv())
            else:
                break
        self.assertTrue(len(messages), 1)
        message = messages[0]

        self.assertEqual(type(message), dict)
        self.assertIn(EVENT_TYPE, message)
        self.assertEqual(message[EVENT_TYPE], EVENT_TYPE_WATCHDOG)
        self.assertIn(WATCHDOG_BASE, message)
        self.assertEqual(message[WATCHDOG_BASE], TEST_MONITOR_BASE)
        self.assertIn(EVENT_PATH, message)
        self.assertEqual(message[EVENT_PATH], os.path.join(start_dir, "A"))
        self.assertIn(EVENT_RULE, message)
        self.assertEqual(message[EVENT_RULE].name, rule.name)

        make_dir(os.path.join(start_dir, "B"))

        messages = []
        while True:
            if from_monitor_reader.poll(5):
                messages.append(from_monitor_reader.recv())
            else:
                break
        self.assertTrue(len(messages), 1)
        message = messages[0]

        self.assertEqual(type(message), dict)
        self.assertIn(EVENT_TYPE, message)
        self.assertEqual(message[EVENT_TYPE], EVENT_TYPE_WATCHDOG)
        self.assertIn(WATCHDOG_BASE, message)
        self.assertEqual(message[WATCHDOG_BASE], TEST_MONITOR_BASE)
        self.assertIn(EVENT_PATH, message)
        self.assertEqual(message[EVENT_PATH], os.path.join(start_dir, "B"))
        self.assertIn(EVENT_RULE, message)
        self.assertEqual(message[EVENT_RULE].name, rule.name)

        wm.stop()

    # Test WatchdogMonitor get_patterns function
    def testMonitorGetPatterns(self)->None:
        pattern_one = FileEventPattern(
            "pattern_one", 
            os.path.join("start", "A.txt"), 
            "recipe_one", 
            "infile", 
            parameters={})
        pattern_two = FileEventPattern(
            "pattern_two", 
            os.path.join("start", "B.txt"), 
            "recipe_two", 
            "infile", 
            parameters={})

        wm = WatchdogMonitor(
            TEST_MONITOR_BASE,
            {
                pattern_one.name: pattern_one,
                pattern_two.name: pattern_two
            },
            {}
        )

        patterns = wm.get_patterns()

        self.assertIsInstance(patterns, dict)
        self.assertEqual(len(patterns), 2)
        self.assertIn(pattern_one.name, patterns)
        patterns_equal(self, patterns[pattern_one.name], pattern_one)
        self.assertIn(pattern_two.name, patterns)
        patterns_equal(self, patterns[pattern_two.name], pattern_two)

    # Test WatchdogMonitor add_pattern function
    def testMonitorAddPattern(self)->None:
        pattern_one = FileEventPattern(
            "pattern_one", 
            os.path.join("start", "A.txt"), 
            "recipe_one", 
            "infile", 
            parameters={})
        pattern_two = FileEventPattern(
            "pattern_two", 
            os.path.join("start", "B.txt"), 
            "recipe_two", 
            "infile", 
            parameters={})

        wm = WatchdogMonitor(
            TEST_MONITOR_BASE,
            {pattern_one.name: pattern_one},
            {}
        )

        patterns = wm.get_patterns()

        self.assertIsInstance(patterns, dict)
        self.assertEqual(len(patterns), 1)
        self.assertIn(pattern_one.name, patterns)
        patterns_equal(self, patterns[pattern_one.name], pattern_one)

        wm.add_pattern(pattern_two)

        patterns = wm.get_patterns()

        self.assertIsInstance(patterns, dict)
        self.assertEqual(len(patterns), 2)
        self.assertIn(pattern_one.name, patterns)
        patterns_equal(self, patterns[pattern_one.name], pattern_one)
        self.assertIn(pattern_two.name, patterns)
        patterns_equal(self, patterns[pattern_two.name], pattern_two)

        with self.assertRaises(KeyError):
            wm.add_pattern(pattern_two)

        patterns = wm.get_patterns()

        self.assertIsInstance(patterns, dict)
        self.assertEqual(len(patterns), 2)
        self.assertIn(pattern_one.name, patterns)
        patterns_equal(self, patterns[pattern_one.name], pattern_one)
        self.assertIn(pattern_two.name, patterns)
        patterns_equal(self, patterns[pattern_two.name], pattern_two)

    # Test WatchdogMonitor update_patterns function
    def testMonitorUpdatePattern(self)->None:
        pattern_one = FileEventPattern(
            "pattern_one", 
            os.path.join("start", "A.txt"), 
            "recipe_one", 
            "infile", 
            parameters={})
        pattern_two = FileEventPattern(
            "pattern_two", 
            os.path.join("start", "B.txt"), 
            "recipe_two", 
            "infile", 
            parameters={})

        wm = WatchdogMonitor(
            TEST_MONITOR_BASE,
            {pattern_one.name: pattern_one},
            {}
        )

        patterns = wm.get_patterns()

        self.assertIsInstance(patterns, dict)
        self.assertEqual(len(patterns), 1)
        self.assertIn(pattern_one.name, patterns)
        patterns_equal(self, patterns[pattern_one.name], pattern_one)

        pattern_one.recipe = "top_secret_recipe"

        patterns = wm.get_patterns()
        self.assertIsInstance(patterns, dict)
        self.assertEqual(len(patterns), 1)
        self.assertIn(pattern_one.name, patterns)
        self.assertEqual(patterns[pattern_one.name].name, 
            pattern_one.name)
        self.assertEqual(patterns[pattern_one.name].recipe, 
            "recipe_one")
        self.assertEqual(patterns[pattern_one.name].parameters, 
            pattern_one.parameters)
        self.assertEqual(patterns[pattern_one.name].outputs, 
            pattern_one.outputs)
        self.assertEqual(patterns[pattern_one.name].triggering_path, 
            pattern_one.triggering_path)
        self.assertEqual(patterns[pattern_one.name].triggering_file, 
            pattern_one.triggering_file)
        self.assertEqual(patterns[pattern_one.name].event_mask, 
            pattern_one.event_mask)
        self.assertEqual(patterns[pattern_one.name].sweep, 
            pattern_one.sweep)

        wm.update_pattern(pattern_one)

        patterns = wm.get_patterns()
        self.assertIsInstance(patterns, dict)
        self.assertEqual(len(patterns), 1)
        self.assertIn(pattern_one.name, patterns)
        patterns_equal(self, patterns[pattern_one.name], pattern_one)

        with self.assertRaises(KeyError):
            wm.update_pattern(pattern_two)

        patterns = wm.get_patterns()
        self.assertIsInstance(patterns, dict)
        self.assertEqual(len(patterns), 1)
        self.assertIn(pattern_one.name, patterns)
        patterns_equal(self, patterns[pattern_one.name], pattern_one)

    # Test WatchdogMonitor remove_patterns function
    def testMonitorRemovePattern(self)->None:
        pattern_one = FileEventPattern(
            "pattern_one", 
            os.path.join("start", "A.txt"), 
            "recipe_one", 
            "infile", 
            parameters={})
        pattern_two = FileEventPattern(
            "pattern_two", 
            os.path.join("start", "B.txt"), 
            "recipe_two", 
            "infile", 
            parameters={})

        wm = WatchdogMonitor(
            TEST_MONITOR_BASE,
            {pattern_one.name: pattern_one},
            {}
        )

        patterns = wm.get_patterns()

        self.assertIsInstance(patterns, dict)
        self.assertEqual(len(patterns), 1)
        self.assertIn(pattern_one.name, patterns)
        patterns_equal(self, patterns[pattern_one.name], pattern_one)

        with self.assertRaises(KeyError):
            wm.remove_pattern(pattern_two)

        patterns = wm.get_patterns()

        self.assertIsInstance(patterns, dict)
        self.assertEqual(len(patterns), 1)
        self.assertIn(pattern_one.name, patterns)
        patterns_equal(self, patterns[pattern_one.name], pattern_one)

        wm.remove_pattern(pattern_one)

        patterns = wm.get_patterns()

        self.assertIsInstance(patterns, dict)
        self.assertEqual(len(patterns), 0)

    # Test WatchdogMonitor get_recipes function
    def testMonitorGetRecipes(self)->None:
        recipe_one = JupyterNotebookRecipe(
            "recipe_one", BAREBONES_NOTEBOOK)
        recipe_two = JupyterNotebookRecipe(
            "recipe_two", BAREBONES_NOTEBOOK)

        wm = WatchdogMonitor(
            TEST_MONITOR_BASE,
            {},
            {
                recipe_one.name: recipe_one,
                recipe_two.name: recipe_two
            }
        )

        recipes = wm.get_recipes()

        self.assertIsInstance(recipes, dict)
        self.assertEqual(len(recipes), 2)
        self.assertIn(recipe_one.name, recipes)
        recipes_equal(self, recipes[recipe_one.name], recipe_one)
        self.assertIn(recipe_two.name, recipes)
        recipes_equal(self, recipes[recipe_two.name], recipe_two)

    # Test WatchdogMonitor add_recipe function
    def testMonitorAddRecipe(self)->None:
        recipe_one = JupyterNotebookRecipe(
            "recipe_one", BAREBONES_NOTEBOOK)
        recipe_two = JupyterNotebookRecipe(
            "recipe_two", BAREBONES_NOTEBOOK)

        wm = WatchdogMonitor(
            TEST_MONITOR_BASE,
            {},
            {
                recipe_one.name: recipe_one
            }
        )

        recipes = wm.get_recipes()

        self.assertIsInstance(recipes, dict)
        self.assertEqual(len(recipes), 1)
        self.assertIn(recipe_one.name, recipes)
        recipes_equal(self, recipes[recipe_one.name], recipe_one)


        wm.add_recipe(recipe_two)

        recipes = wm.get_recipes()

        self.assertIsInstance(recipes, dict)
        self.assertEqual(len(recipes), 2)
        self.assertIn(recipe_one.name, recipes)
        recipes_equal(self, recipes[recipe_one.name], recipe_one)
        self.assertIn(recipe_two.name, recipes)
        recipes_equal(self, recipes[recipe_two.name], recipe_two)

        with self.assertRaises(KeyError):
            wm.add_recipe(recipe_two)

        recipes = wm.get_recipes()

        self.assertIsInstance(recipes, dict)
        self.assertEqual(len(recipes), 2)
        self.assertIn(recipe_one.name, recipes)
        recipes_equal(self, recipes[recipe_one.name], recipe_one)
        self.assertIn(recipe_two.name, recipes)
        recipes_equal(self, recipes[recipe_two.name], recipe_two)

    # Test WatchdogMonitor update_recipe function
    def testMonitorUpdateRecipe(self)->None:
        recipe_one = JupyterNotebookRecipe(
            "recipe_one", BAREBONES_NOTEBOOK)
        recipe_two = JupyterNotebookRecipe(
            "recipe_two", BAREBONES_NOTEBOOK)

        wm = WatchdogMonitor(
            TEST_MONITOR_BASE,
            {},
            {
                recipe_one.name: recipe_one
            }
        )

        recipes = wm.get_recipes()

        self.assertIsInstance(recipes, dict)
        self.assertEqual(len(recipes), 1)
        self.assertIn(recipe_one.name, recipes)
        recipes_equal(self, recipes[recipe_one.name], recipe_one)

        recipe_one.source = "top_secret_source"

        recipes = wm.get_recipes()
        self.assertIsInstance(recipes, dict)
        self.assertEqual(len(recipes), 1)
        self.assertIn(recipe_one.name, recipes)
        self.assertEqual(recipes[recipe_one.name].name, 
            recipe_one.name)
        self.assertEqual(recipes[recipe_one.name].recipe, 
            recipe_one.recipe)
        self.assertEqual(recipes[recipe_one.name].parameters, 
            recipe_one.parameters)
        self.assertEqual(recipes[recipe_one.name].requirements, 
            recipe_one.requirements)
        self.assertEqual(recipes[recipe_one.name].source, 
            "")

        wm.update_recipe(recipe_one)

        recipes = wm.get_recipes()
        self.assertIsInstance(recipes, dict)
        self.assertEqual(len(recipes), 1)
        self.assertIn(recipe_one.name, recipes)
        recipes_equal(self, recipes[recipe_one.name], recipe_one)

        with self.assertRaises(KeyError):
            wm.update_recipe(recipe_two)

        recipes = wm.get_recipes()
        self.assertIsInstance(recipes, dict)
        self.assertEqual(len(recipes), 1)
        self.assertIn(recipe_one.name, recipes)
        recipes_equal(self, recipes[recipe_one.name], recipe_one)

    # Test WatchdogMonitor remove_recipe function
    def testMonitorRemoveRecipe(self)->None:
        recipe_one = JupyterNotebookRecipe(
            "recipe_one", BAREBONES_NOTEBOOK)
        recipe_two = JupyterNotebookRecipe(
            "recipe_two", BAREBONES_NOTEBOOK)

        wm = WatchdogMonitor(
            TEST_MONITOR_BASE,
            {},
            {
                recipe_one.name: recipe_one
            }
        )

        recipes = wm.get_recipes()

        self.assertIsInstance(recipes, dict)
        self.assertEqual(len(recipes), 1)
        self.assertIn(recipe_one.name, recipes)
        recipes_equal(self, recipes[recipe_one.name], recipe_one)

        with self.assertRaises(KeyError):
            wm.remove_recipe(recipe_two)

        recipes = wm.get_recipes()

        self.assertIsInstance(recipes, dict)
        self.assertEqual(len(recipes), 1)
        self.assertIn(recipe_one.name, recipes)
        recipes_equal(self, recipes[recipe_one.name], recipe_one)

        wm.remove_recipe(recipe_one)

        recipes = wm.get_recipes()

        self.assertIsInstance(recipes, dict)
        self.assertEqual(len(recipes), 0)

    # Test WatchdogMonitor get_rules function
    def testMonitorGetRules(self)->None:
        pattern_one = FileEventPattern(
            "pattern_one", 
            os.path.join("start", "A.txt"), 
            "recipe_one", 
            "infile", 
            parameters={})
        pattern_two = FileEventPattern(
            "pattern_two", 
            os.path.join("start", "B.txt"), 
            "recipe_two", 
            "infile", 
            parameters={})
        recipe_one = JupyterNotebookRecipe(
            "recipe_one", BAREBONES_NOTEBOOK)
        recipe_two = JupyterNotebookRecipe(
            "recipe_two", BAREBONES_NOTEBOOK)

        patterns = {
            pattern_one.name: pattern_one,
            pattern_two.name: pattern_two,
        }
        recipes = {
            recipe_one.name: recipe_one,
            recipe_two.name: recipe_two,
        }

        wm = WatchdogMonitor(
            TEST_MONITOR_BASE,
            patterns,
            recipes
        )

        rules = wm.get_rules()

        self.assertIsInstance(rules, dict)
        self.assertEqual(len(rules), 2)

    def testMatch(self)->None:
        p1 = FileEventPattern(
            "p1", 
            os.path.join("dir", "file.txt"),
            "r1",
            "triggerfile"
        )
        p2 = FileEventPattern(
            "p2", 
            os.path.join("dir2", "*"),
            "r1",
            "triggerfile"
        )
        p3 = FileEventPattern(
            "p3", 
            os.path.join("dir3", "*.txt"),
            "r1",
            "triggerfile"
        )
        r1 = SharedTestRecipe(
            "r1",
            ""
        )

        to_test, from_monitor = Pipe()

        patterns = assemble_patterns_dict([ p1, p2, p3 ])
        recipes = assemble_recipes_dict([ r1 ])

        wm = WatchdogMonitor(
            TEST_MONITOR_BASE, 
            patterns, 
            recipes,
            logging=4
        )
        wm.to_runner_event = to_test

        e1 = FileSystemEvent("test")
        e1.event_type = [ "created" ]
        e1.time_stamp = 10

        wm.match(e1)

        message = None
        if from_monitor.poll(3):
            message = from_monitor.recv()

        self.assertIsNone(message)

        e2 = FileSystemEvent(os.path.join("dir", "file.txt"))
        e2.event_type = [ "created" ] 
        e2.time_stamp = 10

        wm.match(e2)

        message = None
        if from_monitor.poll(3):
            message = from_monitor.recv()

        self.assertIsNotNone(message)
        self.assertEqual(e2.src_path, message[EVENT_PATH])
        self.assertEqual(message[EVENT_TYPE], EVENT_TYPE_WATCHDOG)
        self.assertEqual(message[WATCHDOG_BASE], TEST_MONITOR_BASE)

        e3 = FileSystemEvent(os.path.join("dir", "file2.txt"))
        e3.event_type = [ "created" ] 
        e3.time_stamp = 10

        wm.match(e3)

        message = None
        if from_monitor.poll(3):
            message = from_monitor.recv()

        self.assertIsNone(message)

        e4 = FileSystemEvent(os.path.join("dir2", "file.txt"))
        e4.event_type = [ "created" ] 
        e4.time_stamp = 10

        wm.match(e4)

        message = None
        if from_monitor.poll(3):
            message = from_monitor.recv()

        self.assertIsNotNone(message)
        self.assertEqual(e4.src_path, message[EVENT_PATH])
        self.assertEqual(message[EVENT_TYPE], EVENT_TYPE_WATCHDOG)
        self.assertEqual(message[WATCHDOG_BASE], TEST_MONITOR_BASE)

        e4 = FileSystemEvent(os.path.join("dir2", "file2.txt"))
        e4.event_type = [ "created" ] 
        e4.time_stamp = 10

        wm.match(e4)

        message = None
        if from_monitor.poll(3):
            message = from_monitor.recv()

        self.assertIsNotNone(message)
        self.assertEqual(e4.src_path, message[EVENT_PATH])
        self.assertEqual(message[EVENT_TYPE], EVENT_TYPE_WATCHDOG)
        self.assertEqual(message[WATCHDOG_BASE], TEST_MONITOR_BASE)

        e5 = FileSystemEvent(os.path.join("dir2", "dir", "file.txt"))
        e5.event_type = [ "created" ] 
        e5.time_stamp = 10

        wm.match(e5)

        message = None
        if from_monitor.poll(3):
            message = from_monitor.recv()

        self.assertIsNotNone(message)
        self.assertEqual(e5.src_path, message[EVENT_PATH])
        self.assertEqual(message[EVENT_TYPE], EVENT_TYPE_WATCHDOG)
        self.assertEqual(message[WATCHDOG_BASE], TEST_MONITOR_BASE)

        e6 = FileSystemEvent(os.path.join("dir3", "file.txt"))
        e6.event_type = [ "created" ] 
        e6.time_stamp = 10

        wm.match(e6)

        message = None
        if from_monitor.poll(3):
            message = from_monitor.recv()

        self.assertIsNotNone(message)
        self.assertEqual(e6.src_path, message[EVENT_PATH])
        self.assertEqual(message[EVENT_TYPE], EVENT_TYPE_WATCHDOG)
        self.assertEqual(message[WATCHDOG_BASE], TEST_MONITOR_BASE)

        e7 = FileSystemEvent(os.path.join("dir3", "dir", "file.txt"))
        e7.event_type = [ "created" ] 
        e7.time_stamp = 10

        wm.match(e7)

        message = None
        if from_monitor.poll(3):
            message = from_monitor.recv()

        self.assertIsNotNone(message)
        self.assertEqual(e7.src_path, message[EVENT_PATH])
        self.assertEqual(message[EVENT_TYPE], EVENT_TYPE_WATCHDOG)
        self.assertEqual(message[WATCHDOG_BASE], TEST_MONITOR_BASE)

        e8 = FileSystemEvent(os.path.join("dir3", "file"))
        e8.event_type = [ "created" ] 
        e8.time_stamp = 10

        wm.match(e8)

        message = None
        if from_monitor.poll(3):
            message = from_monitor.recv()

        self.assertIsNone(message) 

class WatchdogEventHandlerTests(unittest.TestCase):
    def setUp(self)->None:
        super().setUp()
        setup()

    def tearDown(self)->None:
        super().tearDown()
        teardown()

    def testThreadedHandler(self)->None:
        def alert(event):
            from_mon.send(event)
            
        from_mon, to_test = Pipe()
        wm = WatchdogMonitor(TEST_MONITOR_BASE, {}, {})
        wm.match = alert
        wm.alert_chan = from_mon

        wh = WatchdogEventHandler(wm)

        e1 = FileSystemEvent("test")
        e1.time_stamp = 10.0
        e1.event_type = "created"

        wh.threaded_handler(e1)
        message = None
        if to_test.poll(3):
            message = to_test.recv()

        self.assertIsNotNone(message)
        self.assertEqual(message, e1)
        self.assertEqual(
            wh._recent_jobs, {
                "test": [10.0, {"created"}]
            }
        )

        e2 = FileSystemEvent("test")
        e2.time_stamp = 10.5
        e2.event_type = "modified"

        wh.threaded_handler(e2)
        message = None
        if to_test.poll(3):
            message = to_test.recv()

        self.assertIsNotNone(message)
        self.assertEqual(message, e2)
        self.assertEqual(
            wh._recent_jobs, {
                "test": [10.5, {"modified", "created"}]
            }
        )

        e3 = FileSystemEvent("test")
        e3.time_stamp = 12
        e3.event_type = "moved"

        wh.threaded_handler(e3)
        message = None
        if to_test.poll(3):
            message = to_test.recv()

        self.assertIsNotNone(message)
        self.assertEqual(message, e3)
        self.assertEqual(
            wh._recent_jobs, {
                "test": [12, {"moved"}]
            }
        )

class SocketPatternTests(unittest.TestCase):
    def setUp(self)->None:
        super().setUp()
        setup()

    def tearDown(self)->None:
        super().tearDown()
        teardown()

    # Test NetworkEvent created
    def testSocketPatternCreationMinimum(self)->None:
        SocketPattern("name", TEST_PORT, "recipe", "msg")

    # Test SocketPattern not created with empty name
    def testSocketPatternCreationEmptyName(self)->None:
        with self.assertRaises(ValueError):
            SocketPattern("", 9000, "recipe", "msg")

    # Test SocketPattern not created with empty recipe
    def testSocketPatternCreationEmptyRecipe(self)->None:
        with self.assertRaises(ValueError):
            SocketPattern("name", 9000, "", "msg")

    # Test SocketPattern not created with invalid name
    def testSocketPatternCreationInvalidName(self)->None:
        with self.assertRaises(ValueError):
            SocketPattern("@name", TEST_PORT, "recipe", "msg")

    # Test SocketPattern not created with invalid port
    def testSocketPatternCreationInvalidPort(self)->None:
        with self.assertRaises(ValueError):
            SocketPattern("name", "9000", "recipe", "msg")

    # Test SocketPattern not created with invalid port
    def testSocketPatternCreationInvalidPort2(self)->None:
        with self.assertRaises(ValueError):
            SocketPattern("name", 0, "recipe", "msg")

    # Test SocketPattern not created with invalid recipe
    def testSocketPatternCreationInvalidRecipe(self)->None:
        with self.assertRaises(ValueError):
            SocketPattern("name", TEST_PORT, "@recipe", "msg")

    # Test SocketPattern created with valid name
    def testSocketPatternSetupName(self)->None:
        name = "name"
        nep = SocketPattern(name, TEST_PORT, "recipe", "msg")
        self.assertEqual(nep.name, name)

    # Test SocketPattern created with valid port
    def testSocketPatternSetupPort(self)->None:
        nep = SocketPattern("name", TEST_PORT, "recipe", "msg")
        self.assertEqual(nep.triggering_port, TEST_PORT)

    # Test SocketPattern created with valid recipe
    def testSocketPatternSetupRecipe(self)->None:
        recipe = "recipe"
        nep = SocketPattern("name", TEST_PORT, recipe, "msg")
        self.assertEqual(nep.recipe, recipe)

    # Test SocketPattern created with valid parameters
    def testSocketPatternSetupParameters(self)->None:
        parameters = {
            "a": 1,
            "b": True
        }
        fep = SocketPattern(
            "name", TEST_PORT, "recipe", "msg", parameters=parameters
        )
        self.assertEqual(fep.parameters, parameters)

    # Test SocketPattern created with valid outputs
    def testSocketPatternSetupOutputs(self)->None:
        outputs = {
            "a": "a",
            "b": "b"
        }
        fep = SocketPattern(
            "name", TEST_PORT, "recipe", "msg", outputs=outputs
        )
        self.assertEqual(fep.outputs, outputs)

class SocketMonitorTests(unittest.TestCase):
    def setUp(self)->None:
        self.assertFalse(check_port_in_use(TEST_PORT))          
        self.assertFalse(check_port_in_use(TEST_PORT+1))          
        super().setUp()
        setup()

    def tearDown(self)->None:
        super().tearDown()
        teardown()
        check_shutdown_port_in_timeout(TEST_PORT, 5)
        check_shutdown_port_in_timeout(TEST_PORT+1, 5)

    # Test creation of network event dict
    def testCreateNetworkEvent(self)->None:
        pattern = SocketPattern(
            "pattern",
            TEST_PORT,
            "recipe_one", 
            "msg",
            parameters={
                "extra":"A line from a test Pattern",
                "outfile":"result_path"
            })
        recipe = JupyterNotebookRecipe(
            "recipe_one", APPENDING_NOTEBOOK)

        rule = create_rule(pattern, recipe)

        tmp_file = tempfile.NamedTemporaryFile(
            "wb", delete=True, dir=TEST_MONITOR_BASE
        )
        tmp_file.write(b"data")

        with self.assertRaises(TypeError):
            event = create_socket_file_event(
                tmp_file.name, rule, TEST_MONITOR_BASE
            )

        event = create_socket_file_event(
            tmp_file.name, rule, TEST_MONITOR_BASE, time()
        )

        tmp_file.close()

        self.assertEqual(type(event), dict)
        self.assertEqual(len(event.keys()), len(WATCHDOG_EVENT_KEYS))
        for key, value in WATCHDOG_EVENT_KEYS.items():
            self.assertTrue(key in event.keys())
            self.assertIsInstance(event[key], value)
        self.assertEqual(event[EVENT_TYPE], EVENT_TYPE_WATCHDOG)
        self.assertEqual(
            event[EVENT_PATH], 
            tmp_file.name[tmp_file.name.index(TEST_MONITOR_BASE):]
        )
        self.assertEqual(event[EVENT_RULE], rule)


        tmp_file2 = tempfile.NamedTemporaryFile(
            "wb", delete=True, dir=TEST_MONITOR_BASE
        )
        tmp_file2.write(b"data")
        
        event = create_socket_file_event(
            tmp_file2.name,
            rule,
            TEST_MONITOR_BASE,
            time(),
            extras={"a":1}
        )

        tmp_file2.close()

        self.assertEqual(type(event), dict)
        self.assertTrue(EVENT_TYPE in event.keys())
        self.assertTrue(EVENT_PATH in event.keys())
        self.assertTrue(EVENT_RULE in event.keys())
        self.assertEqual(len(event.keys()), len(WATCHDOG_EVENT_KEYS)+1)
        for key, value in WATCHDOG_EVENT_KEYS.items():
            self.assertTrue(key in event.keys())
            self.assertIsInstance(event[key], value)
        self.assertEqual(event[EVENT_TYPE], EVENT_TYPE_WATCHDOG)
        self.assertEqual(
            event[EVENT_PATH], 
            tmp_file2.name[tmp_file2.name.index(TEST_MONITOR_BASE):]
        )
        self.assertEqual(event[EVENT_RULE], rule)
        self.assertEqual(event["a"], 1)

    # Test SocketMonitor naming
    def testSocketMonitorNaming(self)->None:
        test_name = "test_name"
        monitor = SocketMonitor(TEST_MONITOR_BASE, {}, {}, name=test_name)
        self.assertEqual(monitor.name, test_name)

        monitor = SocketMonitor(TEST_MONITOR_BASE, {}, {})
        self.assertTrue(monitor.name.startswith("monitor_"))

    # Test SocketMonitor identifies expected network events
    def testSocketMonitorEventIdentification(self)->None:
        localhost = "127.0.0.1"
        port = TEST_PORT
        test_packet = b'test'

        from_monitor_reader, from_monitor_writer = Pipe()

        pattern_one = SocketPattern(
            "pattern_one", port, "recipe_one", "msg")
        recipe = JupyterNotebookRecipe(
            "recipe_one", BAREBONES_NOTEBOOK)

        patterns = {
            pattern_one.name: pattern_one,
        }
        recipes = {
            recipe.name: recipe,
        }

        monitor = SocketMonitor(TEST_MONITOR_BASE, patterns, recipes)
        monitor.to_runner_event = from_monitor_writer

        rules = monitor.get_rules()

        self.assertEqual(len(rules), 1)
        rule = rules[list(rules.keys())[0]]

        monitor.start()

        sender = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sender.connect((localhost,port))
        sender.sendall(test_packet)
        sender.close()

        if from_monitor_reader.poll(3):
            message = from_monitor_reader.recv()
        else:
            message = None

        self.assertIsNotNone(message)
        event = message
        self.assertIsInstance(event, dict)

        self.assertTrue(EVENT_TYPE in event.keys())
        self.assertTrue(EVENT_PATH in event.keys())
        self.assertTrue(EVENT_RULE in event.keys())
        for key, value in WATCHDOG_EVENT_KEYS.items():
            self.assertTrue(key in event.keys())
            self.assertIsInstance(event[key], value)
        self.assertEqual(event[EVENT_TYPE], EVENT_TYPE_WATCHDOG)
        self.assertEqual(event[EVENT_RULE].name, rule.name)

        with open(event[EVENT_PATH], "rb") as file_pointer:
            received_packet = file_pointer.read()

        self.assertEqual(received_packet, test_packet)

        monitor.stop()

    # Test SocketMonitor get_patterns function
    def testSocketMonitorGetPatterns(self)->None:
        pattern_one = SocketPattern(
            "pattern_one",
            TEST_PORT,
            "recipe_one", 
            "msg",
            parameters={})
        pattern_two = SocketPattern(
            "pattern_two",
            TEST_PORT+1,
            "recipe_two", 
            "msg",
            parameters={})

        monitor = SocketMonitor(
            TEST_MONITOR_BASE, 
            {
                pattern_one.name: pattern_one,
                pattern_two.name: pattern_two
            },
            {}
        )

        patterns = monitor.get_patterns()

        self.assertIsInstance(patterns, dict)
        self.assertEqual(len(patterns), 2)
        self.assertIn(pattern_one.name, patterns)
        patterns_equal(self, patterns[pattern_one.name], pattern_one)
        self.assertIn(pattern_two.name, patterns)
        patterns_equal(self, patterns[pattern_two.name], pattern_two)

    # Test SocketMonitor add_pattern function
    def testSocketAddPattern(self)->None:
        pattern_one = SocketPattern(
            "pattern_one",
            TEST_PORT,
            "recipe_one", 
            "msg",
            parameters={})
        pattern_two = SocketPattern(
            "pattern_two",
            TEST_PORT+1,
            "recipe_two", 
            "msg",
            parameters={})

        monitor = SocketMonitor(
            TEST_MONITOR_BASE, 
            {
                pattern_one.name: pattern_one
            },
            {}
        )

        self.assertEqual(len(monitor._rules), 0)
        self.assertEqual(len(monitor.ports), 0)
        self.assertEqual(len(monitor.listeners), 0)

        patterns = monitor.get_patterns()

        self.assertIsInstance(patterns, dict)
        self.assertEqual(len(patterns), 1)
        self.assertIn(pattern_one.name, patterns)
        patterns_equal(self, patterns[pattern_one.name], pattern_one)

        monitor.add_pattern(pattern_two)

        self.assertEqual(len(monitor._rules), 0)
        self.assertEqual(len(monitor.ports), 0)
        self.assertEqual(len(monitor.listeners), 0)

        patterns = monitor.get_patterns()

        self.assertIsInstance(patterns, dict)
        self.assertEqual(len(patterns), 2)
        self.assertIn(pattern_one.name, patterns)
        patterns_equal(self, patterns[pattern_one.name], pattern_one)
        self.assertIn(pattern_two.name, patterns)
        patterns_equal(self, patterns[pattern_two.name], pattern_two)

        with self.assertRaises(KeyError):
            monitor.add_pattern(pattern_two)

        self.assertEqual(len(monitor._rules), 0)
        self.assertEqual(len(monitor.ports), 0)
        self.assertEqual(len(monitor.listeners), 0)

        patterns = monitor.get_patterns()

        self.assertIsInstance(patterns, dict)
        self.assertEqual(len(patterns), 2)
        self.assertIn(pattern_one.name, patterns)
        patterns_equal(self, patterns[pattern_one.name], pattern_one)
        self.assertIn(pattern_two.name, patterns)
        patterns_equal(self, patterns[pattern_two.name], pattern_two)

        self.assertEqual(len(monitor._rules), 0)
        self.assertEqual(len(monitor.ports), 0)
        self.assertEqual(len(monitor.listeners), 0)

    # Test SocketMonitor update_patterns function
    def testMonitorUpdatePattern(self)->None:
        pattern_one = SocketPattern(
            "pattern_one",
            TEST_PORT,
            "recipe_one", 
            "msg",
            parameters={})
        pattern_two = SocketPattern(
            "pattern_two",
            TEST_PORT+1,
            "recipe_two", 
            "msg",
            parameters={})

        monitor = SocketMonitor(
            TEST_MONITOR_BASE, 
            {
                pattern_one.name: pattern_one
            },
            {}
        )

        patterns = monitor.get_patterns()

        self.assertIsInstance(patterns, dict)
        self.assertEqual(len(patterns), 1)
        self.assertIn(pattern_one.name, patterns)
        patterns_equal(self, patterns[pattern_one.name], pattern_one)

        pattern_one.recipe = "top_secret_recipe"

        patterns = monitor.get_patterns()
        self.assertIsInstance(patterns, dict)
        self.assertEqual(len(patterns), 1)
        self.assertIn(pattern_one.name, patterns)
        self.assertEqual(patterns[pattern_one.name].name,
            pattern_one.name)
        self.assertEqual(patterns[pattern_one.name].recipe,
            "recipe_one")
        self.assertEqual(patterns[pattern_one.name].parameters,
            pattern_one.parameters)
        self.assertEqual(patterns[pattern_one.name].outputs,
            pattern_one.outputs)
        self.assertEqual(patterns[pattern_one.name].triggering_port,
            pattern_one.triggering_port)

        monitor.update_pattern(pattern_one)

        patterns = monitor.get_patterns()
        self.assertIsInstance(patterns, dict)
        self.assertEqual(len(patterns), 1)
        self.assertIn(pattern_one.name, patterns)
        patterns_equal(self, patterns[pattern_one.name], pattern_one)

        with self.assertRaises(KeyError):
            monitor.update_pattern(pattern_two)

        patterns = monitor.get_patterns()
        self.assertIsInstance(patterns, dict)
        self.assertEqual(len(patterns), 1)
        self.assertIn(pattern_one.name, patterns)
        patterns_equal(self, patterns[pattern_one.name], pattern_one)

    # Test SocketMonitor remove_patterns function
    def testMonitorRemovePattern(self)->None:
        pattern_one = SocketPattern(
            "pattern_one",
            TEST_PORT,
            "recipe_one", 
            "msg",
            parameters={})
        pattern_two = SocketPattern(
            "pattern_two",
            TEST_PORT+1,
            "recipe_two", 
            "msg",
            parameters={})

        monitor = SocketMonitor(
            TEST_MONITOR_BASE, 
            {
                pattern_one.name: pattern_one
            },
            {}
        )

        patterns = monitor.get_patterns()

        self.assertIsInstance(patterns, dict)
        self.assertEqual(len(patterns), 1)
        self.assertIn(pattern_one.name, patterns)
        patterns_equal(self, patterns[pattern_one.name], pattern_one)

        with self.assertRaises(KeyError):
            monitor.remove_pattern(pattern_two)

        patterns = monitor.get_patterns()

        self.assertIsInstance(patterns, dict)
        self.assertEqual(len(patterns), 1)
        self.assertIn(pattern_one.name, patterns)
        patterns_equal(self, patterns[pattern_one.name], pattern_one)

        monitor.remove_pattern(pattern_one)

        patterns = monitor.get_patterns()

        self.assertIsInstance(patterns, dict)
        self.assertEqual(len(patterns), 0)

    # Test SocketMonitor get_recipes function
    def testMonitorGetRecipes(self)->None:
        recipe_one = JupyterNotebookRecipe(
            "recipe_one", BAREBONES_NOTEBOOK)
        recipe_two = JupyterNotebookRecipe(
            "recipe_two", BAREBONES_NOTEBOOK)

        monitor = SocketMonitor(
            TEST_MONITOR_BASE, 
            {},
            {
                recipe_one.name: recipe_one,
                recipe_two.name: recipe_two
            }
        )

        recipes = monitor.get_recipes()

        self.assertIsInstance(recipes, dict)
        self.assertEqual(len(recipes), 2)
        self.assertIn(recipe_one.name, recipes)
        recipes_equal(self, recipes[recipe_one.name], recipe_one)
        self.assertIn(recipe_two.name, recipes)
        recipes_equal(self, recipes[recipe_two.name], recipe_two)

    # Test SocketMonitor add_recipe function
    def testMonitorAddRecipe(self)->None:
        recipe_one = JupyterNotebookRecipe(
            "recipe_one", BAREBONES_NOTEBOOK)
        recipe_two = JupyterNotebookRecipe(
            "recipe_two", BAREBONES_NOTEBOOK)

        monitor = SocketMonitor(
            TEST_MONITOR_BASE, 
            {},
            {
                recipe_one.name: recipe_one
            }
        )

        recipes = monitor.get_recipes()

        self.assertIsInstance(recipes, dict)
        self.assertEqual(len(recipes), 1)
        self.assertIn(recipe_one.name, recipes)
        recipes_equal(self, recipes[recipe_one.name], recipe_one)


        monitor.add_recipe(recipe_two)

        recipes = monitor.get_recipes()

        self.assertIsInstance(recipes, dict)
        self.assertEqual(len(recipes), 2)
        self.assertIn(recipe_one.name, recipes)
        recipes_equal(self, recipes[recipe_one.name], recipe_one)
        self.assertIn(recipe_two.name, recipes)
        recipes_equal(self, recipes[recipe_two.name], recipe_two)

        with self.assertRaises(KeyError):
            monitor.add_recipe(recipe_two)

        recipes = monitor.get_recipes()

        self.assertIsInstance(recipes, dict)
        self.assertEqual(len(recipes), 2)
        self.assertIn(recipe_one.name, recipes)
        recipes_equal(self, recipes[recipe_one.name], recipe_one)
        self.assertIn(recipe_two.name, recipes)
        recipes_equal(self, recipes[recipe_two.name], recipe_two)

    # Test SocketMonitor update_recipe function
    def testMonitorUpdateRecipe(self)->None:
        recipe_one = JupyterNotebookRecipe(
            "recipe_one", BAREBONES_NOTEBOOK)
        recipe_two = JupyterNotebookRecipe(
            "recipe_two", BAREBONES_NOTEBOOK)

        monitor = SocketMonitor(
            TEST_MONITOR_BASE, 
            {},
            {
                recipe_one.name: recipe_one
            }
        )

        recipes = monitor.get_recipes()

        self.assertIsInstance(recipes, dict)
        self.assertEqual(len(recipes), 1)
        self.assertIn(recipe_one.name, recipes)
        recipes_equal(self, recipes[recipe_one.name], recipe_one)

        recipe_one.source = "top_secret_source"

        recipes = monitor.get_recipes()
        self.assertIsInstance(recipes, dict)
        self.assertEqual(len(recipes), 1)
        self.assertIn(recipe_one.name, recipes)
        self.assertEqual(recipes[recipe_one.name].name,
            recipe_one.name)
        self.assertEqual(recipes[recipe_one.name].recipe,
            recipe_one.recipe)
        self.assertEqual(recipes[recipe_one.name].parameters,
            recipe_one.parameters)
        self.assertEqual(recipes[recipe_one.name].requirements,
            recipe_one.requirements)
        self.assertEqual(recipes[recipe_one.name].source,
            "")

        monitor.update_recipe(recipe_one)

        recipes = monitor.get_recipes()
        self.assertIsInstance(recipes, dict)
        self.assertEqual(len(recipes), 1)
        self.assertIn(recipe_one.name, recipes)
        recipes_equal(self, recipes[recipe_one.name], recipe_one)

        with self.assertRaises(KeyError):
            monitor.update_recipe(recipe_two)

        recipes = monitor.get_recipes()
        self.assertIsInstance(recipes, dict)
        self.assertEqual(len(recipes), 1)
        self.assertIn(recipe_one.name, recipes)
        recipes_equal(self, recipes[recipe_one.name], recipe_one)

    # Test SocketMonitor remove_recipe function
    def testMonitorRemoveRecipe(self)->None:
        recipe_one = JupyterNotebookRecipe(
            "recipe_one", BAREBONES_NOTEBOOK)
        recipe_two = JupyterNotebookRecipe(
            "recipe_two", BAREBONES_NOTEBOOK)

        monitor = SocketMonitor(
            TEST_MONITOR_BASE, 
            {},
            {
                recipe_one.name: recipe_one
            }
        )

        recipes = monitor.get_recipes()

        self.assertIsInstance(recipes, dict)
        self.assertEqual(len(recipes), 1)
        self.assertIn(recipe_one.name, recipes)
        recipes_equal(self, recipes[recipe_one.name], recipe_one)

        with self.assertRaises(KeyError):
            monitor.remove_recipe(recipe_two)

        recipes = monitor.get_recipes()

        self.assertIsInstance(recipes, dict)
        self.assertEqual(len(recipes), 1)
        self.assertIn(recipe_one.name, recipes)
        recipes_equal(self, recipes[recipe_one.name], recipe_one)

        monitor.remove_recipe(recipe_one)

        recipes = monitor.get_recipes()

        self.assertIsInstance(recipes, dict)
        self.assertEqual(len(recipes), 0)

    # Test SocketMonitor get_rules function
    def testMonitorGetRules(self)->None:
        pattern_one = SocketPattern(
            "pattern_one",
            TEST_PORT,
            "recipe_one", 
            "msg",
            parameters={})
        pattern_two = SocketPattern(
            "pattern_two",
            TEST_PORT+1,
            "recipe_two", 
            "msg",
            parameters={})
        recipe_one = JupyterNotebookRecipe(
            "recipe_one", BAREBONES_NOTEBOOK)
        recipe_two = JupyterNotebookRecipe(
            "recipe_two", BAREBONES_NOTEBOOK)

        patterns = {
            pattern_one.name: pattern_one,
            pattern_two.name: pattern_two,
        }
        recipes = {
            recipe_one.name: recipe_one,
            recipe_two.name: recipe_two,
        }

        monitor = SocketMonitor(
            TEST_MONITOR_BASE, 
            patterns,
            recipes
        )

        rules = monitor.get_rules()

        self.assertIsInstance(rules, dict)
        self.assertEqual(len(rules), 2)

    # Test if the rules are updated correctly
    def testSocketUpdateRules(self)->None:
        pattern_one = SocketPattern(
            "pattern_one",
            TEST_PORT,
            "recipe_one", 
            "msg",
            parameters={})
        recipe_one = JupyterNotebookRecipe(
            "recipe_one", BAREBONES_NOTEBOOK)

        patterns = {
            pattern_one.name: pattern_one,
        }

        monitor = SocketMonitor(
            TEST_MONITOR_BASE, 
            patterns,
            {}
        )

        rules = monitor.get_rules()

        self.assertIsInstance(rules, dict)
        self.assertEqual(len(rules), 0)

        monitor.add_recipe(recipe_one)

        rules = monitor.get_rules()

        self.assertIsInstance(rules, dict)
        self.assertEqual(len(rules), 1)

        monitor.stop()

    # Test if the listeners are updated correctly
    def testSocketListeners(self)->None:
        pattern_one = SocketPattern(
            "pattern_one",
            TEST_PORT,
            "recipe_one", 
            "msg",
            parameters={})
        pattern_two = SocketPattern(
            "pattern_two",
            TEST_PORT,
            "recipe_one", 
            "msg",
            parameters={})
        recipe_one = JupyterNotebookRecipe(
            "recipe_one", BAREBONES_NOTEBOOK)

        patterns = {
            pattern_one.name: pattern_one,
        }

        self.assertFalse(check_port_in_use(TEST_PORT))

        monitor = SocketMonitor(
            TEST_MONITOR_BASE, 
            patterns,
            {}
        )

        self.assertFalse(check_port_in_use(TEST_PORT))

        monitor.start()
        self.assertEqual(len(monitor._rules), 0)
        self.assertEqual(len(monitor.ports), 0)
        self.assertEqual(len(monitor.listeners), 0)

        self.assertFalse(check_port_in_use(TEST_PORT))
    
        monitor.add_recipe(recipe_one)

        self.assertEqual(len(monitor._rules), 1)
        self.assertEqual(len(monitor.ports), 1)
        self.assertEqual(len(monitor.listeners), 1)

        sleep(1)

        self.assertTrue(check_port_in_use(TEST_PORT))

        monitor.add_pattern(pattern_two)

        self.assertEqual(len(monitor._rules), 2)
        self.assertEqual(len(monitor.ports), 1)
        self.assertEqual(len(monitor.listeners), 1)

        monitor.remove_recipe(recipe_one)

        self.assertEqual(len(monitor._rules), 0)
        self.assertEqual(len(monitor.ports), 0)
        self.assertEqual(len(monitor.listeners), 0)

        sleep(1)

        self.assertFalse(check_port_in_use(TEST_PORT))
        
        monitor.stop()

    # Test if the listeners are updated correctly
    def testSocketMonitoring(self)->None:
        pattern_one = SocketPattern(
            "pattern_one",
            TEST_PORT,
            "recipe_one", 
            "msg",
            parameters={})
        recipe_one = JupyterNotebookRecipe(
            "recipe_one", BAREBONES_NOTEBOOK)

        patterns = {
            pattern_one.name: pattern_one,
        }

        recipes = {
            recipe_one.name: recipe_one
        }

        sm = SocketMonitor(
            TEST_MONITOR_BASE, 
            patterns,
            recipes
        )

        from_monitor_reader, from_monitor_writer = Pipe()
        sm.to_runner_event = from_monitor_writer

        rules = sm.get_rules()
        self.assertEqual(len(rules), 1)
        rule = rules[list(rules.keys())[0]]

        sm.start()

        sleep(1)

        sender = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sender.connect(("127.0.0.1", TEST_PORT))
        sender.sendall(b"data")
        sender.close()

        messages = []
        while True:
            if from_monitor_reader.poll(3):
                messages.append(from_monitor_reader.recv())
            else:
                break
        self.assertTrue(len(messages), 1)
        message = messages[0]

        self.assertEqual(type(message), dict)
        self.assertIn(EVENT_TYPE, message)
        self.assertEqual(message[EVENT_TYPE], EVENT_TYPE_WATCHDOG)
        self.assertIn(WATCHDOG_BASE, message)
        self.assertEqual(message[WATCHDOG_BASE], TEST_MONITOR_BASE)
        self.assertIn(EVENT_PATH, message)
        self.assertIn(EVENT_RULE, message)
        self.assertEqual(message[EVENT_RULE].name, rule.name)

        with self.assertRaises(ConnectionRefusedError):
            sender = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sender.connect(("127.0.0.1", 8184))
            sender.sendall(b"data")
            sender.close()

        sm.stop()


