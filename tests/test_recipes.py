
import io
import jsonschema
import os
import unittest

from multiprocessing import Pipe
from time import sleep
from watchdog.events import FileCreatedEvent

from patterns.file_event_pattern import FileEventPattern
from recipes.jupyter_notebook_recipe import JupyterNotebookRecipe, \
    PapermillHandler, BASE_FILE, META_FILE, PARAMS_FILE, JOB_FILE, RESULT_FILE
from rules.file_event_jupyter_notebook_rule import FileEventJupyterNotebookRule
from core.correctness.vars import BAREBONES_NOTEBOOK, TEST_HANDLER_BASE, \
    TEST_JOB_OUTPUT, TEST_MONITOR_BASE, COMPLETE_NOTEBOOK
from core.functionality import rmtree, make_dir, create_rules, read_notebook

class CorrectnessTests(unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        make_dir(TEST_MONITOR_BASE)
        make_dir(TEST_HANDLER_BASE)
        make_dir(TEST_JOB_OUTPUT)

    def tearDown(self) -> None:
        super().tearDown()
        rmtree(TEST_MONITOR_BASE)
        rmtree(TEST_HANDLER_BASE)
        rmtree(TEST_JOB_OUTPUT)

    def testJupyterNotebookRecipeCreationMinimum(self)->None:
        JupyterNotebookRecipe("test_recipe", BAREBONES_NOTEBOOK)

    def testJupyterNotebookRecipeCreationSource(self)->None:
        JupyterNotebookRecipe(
            "test_recipe", BAREBONES_NOTEBOOK, source="notebook.ipynb")

    def testJupyterNotebookRecipeCreationNoName(self)->None:
        with self.assertRaises(ValueError):
            JupyterNotebookRecipe("", BAREBONES_NOTEBOOK)

    def testJupyterNotebookRecipeCreationInvalidName(self)->None:
        with self.assertRaises(ValueError):
            JupyterNotebookRecipe("@test_recipe", BAREBONES_NOTEBOOK)

    def testJupyterNotebookRecipeCreationInvalidRecipe(self)->None:
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            JupyterNotebookRecipe("test_recipe", {})

    def testJupyterNotebookRecipeCreationInvalidSourceExtension(self)->None:
        with self.assertRaises(ValueError):
            JupyterNotebookRecipe(
                "test_recipe", BAREBONES_NOTEBOOK, source="notebook")

    def testJupyterNotebookRecipeCreationInvalidSoureChar(self)->None:
        with self.assertRaises(ValueError):
            JupyterNotebookRecipe(
                "test_recipe", BAREBONES_NOTEBOOK, source="@notebook.ipynb")

    def testJupyterNotebookRecipeSetupName(self)->None:
        name = "name"
        jnr = JupyterNotebookRecipe(name, BAREBONES_NOTEBOOK)
        self.assertEqual(jnr.name, name)

    def testJupyterNotebookRecipeSetupRecipe(self)->None:
        jnr = JupyterNotebookRecipe("name", BAREBONES_NOTEBOOK)
        self.assertEqual(jnr.recipe, BAREBONES_NOTEBOOK)

    def testJupyterNotebookRecipeSetupParameters(self)->None:
        parameters = {
            "a": 1,
            "b": True
        }
        jnr = JupyterNotebookRecipe(
            "name", BAREBONES_NOTEBOOK, parameters=parameters)
        self.assertEqual(jnr.parameters, parameters)

    def testJupyterNotebookRecipeSetupRequirements(self)->None:
        requirements = {
            "a": 1,
            "b": True
        }
        jnr = JupyterNotebookRecipe(
            "name", BAREBONES_NOTEBOOK, requirements=requirements)
        self.assertEqual(jnr.requirements, requirements)

    def testJupyterNotebookRecipeSetupSource(self)->None:
        source = "source.ipynb"
        jnr = JupyterNotebookRecipe(
            "name", BAREBONES_NOTEBOOK, source=source)
        self.assertEqual(jnr.source, source)

    def testPapermillHanderMinimum(self)->None:
        monitor_to_handler_reader, _ = Pipe()

        PapermillHandler(
            [monitor_to_handler_reader], 
            TEST_HANDLER_BASE, 
            TEST_JOB_OUTPUT
        )

    def testPapermillHanderStartStop(self)->None:
        monitor_to_handler_reader, _ = Pipe()

        ph = PapermillHandler(
            [monitor_to_handler_reader], 
            TEST_HANDLER_BASE,
            TEST_JOB_OUTPUT
        )
 
        ph.start()
        ph.stop()

    def testPapermillHanderRepeatedStarts(self)->None:
        monitor_to_handler_reader, _ = Pipe()

        ph = PapermillHandler(
            [monitor_to_handler_reader], 
            TEST_HANDLER_BASE,
            TEST_JOB_OUTPUT
        )

        ph.start()
        with self.assertRaises(RuntimeWarning):
            ph.start()
        ph.stop()

    def testPapermillHanderStopBeforeStart(self)->None:
        monitor_to_handler_reader, _ = Pipe()

        ph = PapermillHandler(
            [monitor_to_handler_reader], 
            TEST_HANDLER_BASE,
            TEST_JOB_OUTPUT
        )

        with self.assertRaises(RuntimeWarning):
            ph.stop()

    def testPapermillHandlerHandling(self)->None:
        monitor_to_handler_reader, to_handler = Pipe()

        debug_stream = io.StringIO("")

        ph = PapermillHandler(
            [monitor_to_handler_reader], 
            TEST_HANDLER_BASE,
            TEST_JOB_OUTPUT,
            print=debug_stream,
            logging=3
        )
        
        with open(os.path.join(TEST_MONITOR_BASE, "A"), "w") as f:
            f.write("Data")
        event = FileCreatedEvent(os.path.join(TEST_MONITOR_BASE, "A"))
        event.monitor_base = TEST_MONITOR_BASE

        pattern_one = FileEventPattern(
            "pattern_one", "A", "recipe_one", "file_one")
        recipe = JupyterNotebookRecipe(
            "recipe_one", COMPLETE_NOTEBOOK)

        patterns = {
            pattern_one.name: pattern_one,
        }
        recipes = {
            recipe.name: recipe,
        }

        rules = create_rules(patterns, recipes)
        self.assertEqual(len(rules), 1)
        _, rule = rules.popitem()
        self.assertIsInstance(rule, FileEventJupyterNotebookRule)

        self.assertEqual(len(os.listdir(TEST_JOB_OUTPUT)), 0)

        ph.start()
        to_handler.send((event, rule))

        loops = 0
        job_id = None
        while loops < 15:
            sleep(1)
            debug_stream.seek(0)
            messages = debug_stream.readlines()

            for msg in messages:
                self.assertNotIn("ERROR", msg)
            
                if "INFO: Completed job " in msg:
                    job_id = msg.replace("INFO: Completed job ", "")
                    job_id = job_id[:job_id.index(" with output")]
                    loops = 15
            loops += 1

        self.assertIsNotNone(job_id)
        self.assertEqual(len(os.listdir(TEST_JOB_OUTPUT)), 1)
        self.assertIn(job_id, os.listdir(TEST_JOB_OUTPUT))

        job_dir = os.path.join(TEST_JOB_OUTPUT, job_id)
        self.assertEqual(len(os.listdir(job_dir)), 5)

        self.assertIn(META_FILE, os.listdir(job_dir))
        self.assertIn(BASE_FILE, os.listdir(job_dir))
        self.assertIn(PARAMS_FILE, os.listdir(job_dir))
        self.assertIn(JOB_FILE, os.listdir(job_dir))
        self.assertIn(RESULT_FILE, os.listdir(job_dir))

        result = read_notebook(os.path.join(job_dir, RESULT_FILE))

        self.assertEqual("124875.0\n", 
            result["cells"][4]["outputs"][0]["text"][0])

        ph.stop()
