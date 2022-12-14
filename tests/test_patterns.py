
import os
import unittest

from multiprocessing import Pipe

from core.correctness.vars import FILE_EVENTS, FILE_CREATE_EVENT, \
    BAREBONES_NOTEBOOK, TEST_MONITOR_BASE
from core.functionality import create_rules, rmtree, make_dir
from patterns.file_event_pattern import FileEventPattern, WatchdogMonitor, \
    _DEFAULT_MASK, SWEEP_START, SWEEP_STOP, SWEEP_JUMP
from recipes import JupyterNotebookRecipe

class CorrectnessTests(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        make_dir(TEST_MONITOR_BASE, ensure_clean=True)

    def tearDown(self) -> None:
        super().tearDown()
        rmtree(TEST_MONITOR_BASE)

    def testFileEventPatternCreationMinimum(self)->None:
        FileEventPattern("name", "path", "recipe", "file")

    def testFileEventPatternCreationEmptyName(self)->None:
        with self.assertRaises(ValueError):
            FileEventPattern("", "path", "recipe", "file")

    def testFileEventPatternCreationEmptyPath(self)->None:
        with self.assertRaises(ValueError):
            FileEventPattern("name", "", "recipe", "file")

    def testFileEventPatternCreationEmptyRecipe(self)->None:
        with self.assertRaises(ValueError):
            FileEventPattern("name", "path", "", "file")

    def testFileEventPatternCreationEmptyFile(self)->None:
        with self.assertRaises(ValueError):
            FileEventPattern("name", "path", "recipe", "")

    def testFileEventPatternCreationInvalidName(self)->None:
        with self.assertRaises(ValueError):
            FileEventPattern("@name", "path", "recipe", "file")

    def testFileEventPatternCreationInvalidRecipe(self)->None:
        with self.assertRaises(ValueError):
            FileEventPattern("name", "path", "@recipe", "file")

    def testFileEventPatternCreationInvalidFile(self)->None:
        with self.assertRaises(ValueError):
            FileEventPattern("name", "path", "recipe", "@file")

    def testFileEventPatternSetupName(self)->None:
        name = "name"
        fep = FileEventPattern(name, "path", "recipe", "file")
        self.assertEqual(fep.name, name)

    def testFileEventPatternSetupPath(self)->None:
        path = "path"
        fep = FileEventPattern("name", path, "recipe", "file")
        self.assertEqual(fep.triggering_path, path)

    def testFileEventPatternSetupRecipe(self)->None:
        recipe = "recipe"
        fep = FileEventPattern("name", "path", recipe, "file")
        self.assertEqual(fep.recipe, recipe)

    def testFileEventPatternSetupFile(self)->None:
        file = "file"
        fep = FileEventPattern("name", "path", "recipe", file)
        self.assertEqual(fep.triggering_file, file)

    def testFileEventPatternSetupParementers(self)->None:
        parameters = {
            "a": 1,
            "b": True
        }
        fep = FileEventPattern(
            "name", "path", "recipe", "file", parameters=parameters)
        self.assertEqual(fep.parameters, parameters)

    def testFileEventPatternSetupOutputs(self)->None:
        outputs = {
            "a": "a",
            "b": "b"
        }
        fep = FileEventPattern(
            "name", "path", "recipe", "file", outputs=outputs)
        self.assertEqual(fep.outputs, outputs)

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


    def testWatchdogMonitorMinimum(self)->None:
        from_monitor = Pipe()
        WatchdogMonitor(TEST_MONITOR_BASE, {}, from_monitor[1])

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
        rules = create_rules(patterns, recipes)

        wm = WatchdogMonitor(TEST_MONITOR_BASE, rules, from_monitor_writer)

        wm.start()

        open(os.path.join(TEST_MONITOR_BASE, "A"), "w")
        if from_monitor_reader.poll(3):
            message = from_monitor_reader.recv()

        self.assertIsNotNone(message)
        event, rule = message
        self.assertIsNotNone(event)
        self.assertIsNotNone(rule)
        self.assertEqual(event.src_path, os.path.join(TEST_MONITOR_BASE, "A"))

        open(os.path.join(TEST_MONITOR_BASE, "B"), "w")
        if from_monitor_reader.poll(3):
            new_message = from_monitor_reader.recv()
        else:
            new_message = None
        self.assertIsNone(new_message)

        wm.stop()
