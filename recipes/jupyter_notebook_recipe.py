
import copy
import nbformat
import os
import papermill
import shutil
import sys
import threading

from datetime import datetime
from multiprocessing import Pipe
from time import sleep
from typing import Any
from watchdog.events import FileSystemEvent

from core.correctness.validation import check_type, valid_string, \
    valid_dict, valid_path, valid_list, valid_existing_dir_path, \
    setup_debugging
from core.correctness.vars import VALID_VARIABLE_NAME_CHARS, VALID_CHANNELS, \
    SHA256, DEBUG_ERROR, DEBUG_WARNING, DEBUG_INFO
from core.functionality import wait, get_file_hash, generate_id, make_dir, \
    write_yaml, write_notebook, get_file_hash, parameterize_jupyter_notebook, \
    print_debug
from core.meow import BaseRecipe, BaseHandler, BaseRule
from patterns.file_event_pattern import SWEEP_START, SWEEP_STOP, SWEEP_JUMP

# mig trigger keyword replacements
KEYWORD_PATH = "{PATH}"
KEYWORD_REL_PATH = "{REL_PATH}"
KEYWORD_DIR = "{DIR}"
KEYWORD_REL_DIR = "{REL_DIR}"
KEYWORD_FILENAME = "{FILENAME}"
KEYWORD_PREFIX = "{PREFIX}"
KEYWORD_BASE = "{VGRID}"
KEYWORD_EXTENSION = "{EXTENSION}"
KEYWORD_JOB = "{JOB}"

# job definitions
JOB_ID = 'id'
JOB_PATTERN = 'pattern'
JOB_RECIPE = 'recipe'
JOB_RULE = 'rule'
JOB_PATH = 'path'
JOB_HASH = 'hash'
JOB_STATUS = 'status'
JOB_CREATE_TIME = 'create'
JOB_START_TIME = 'start'
JOB_END_TIME = 'end'
JOB_ERROR = 'error'
JOB_REQUIREMENTS = 'requirements'

# job statuses
STATUS_QUEUED = 'queued'
STATUS_RUNNING = 'running'
STATUS_SKIPPED = 'skipped'
STATUS_FAILED = 'failed'
STATUS_DONE = 'done'

# job definition files
META_FILE = 'job.yml'
BASE_FILE = 'base.ipynb'
PARAMS_FILE = 'params.yml'
JOB_FILE = 'job.ipynb'
RESULT_FILE = 'result.ipynb'

class JupyterNotebookRecipe(BaseRecipe):
    source:str
    def __init__(self, name:str, recipe:Any, parameters:dict[str,Any]={}, 
            requirements:dict[str,Any]={}, source:str=""):
        super().__init__(name, recipe, parameters, requirements)
        self._is_valid_source(source)
        self.source = source

    def _is_valid_source(self, source:str)->None:
        if source:
            valid_path(source, extension=".ipynb", min_length=0)

    def _is_valid_recipe(self, recipe:dict[str,Any])->None:
        check_type(recipe, dict)
        nbformat.validate(recipe)

    def _is_valid_parameters(self, parameters:dict[str,Any])->None:
        valid_dict(parameters, str, Any, strict=False, min_length=0)
        for k in parameters.keys():
            valid_string(k, VALID_VARIABLE_NAME_CHARS)

    def _is_valid_requirements(self, requirements:dict[str,Any])->None:
        valid_dict(requirements, str, Any, strict=False, min_length=0)
        for k in requirements.keys():
            valid_string(k, VALID_VARIABLE_NAME_CHARS)

class PapermillHandler(BaseHandler):
    handler_base:str
    output_dir:str
    debug_level:int
    _worker:threading.Thread
    _stop_pipe:Pipe
    _jobs:list[str]
    _jobs_lock:threading.Lock
    _print_target:Any
    def __init__(self, inputs:list[VALID_CHANNELS], handler_base:str, 
            output_dir:str, print:Any=sys.stdout, logging:int=0)->None:
        super().__init__(inputs)
        self._is_valid_handler_base(handler_base)
        self.handler_base = handler_base
        self._is_valid_output_dir(output_dir)
        self.output_dir = output_dir
        self._print_target, self.debug_level = setup_debugging(print, logging)       
        self._worker = None
        self._stop_pipe = Pipe()
        self._jobs = []
        self._jobs_lock = threading.Lock()
        print_debug(self._print_target, self.debug_level, 
            "Created new PapermillHandler instance", DEBUG_INFO)

    def run(self)->None:
        all_inputs = self.inputs + [self._stop_pipe[0]]
        while True:
            ready = wait(all_inputs)

            if self._stop_pipe[0] in ready:
                return
            else:
                for input in self.inputs:
                    if input in ready:
                        message = input.recv()
                        event, rule = message
                        self.handle(event, rule)

    def start(self)->None:
        if self._worker is None:
            self._worker = threading.Thread(
                target=self.run,
                args=[])
            self._worker.daemon = True
            self._worker.start()
            print_debug(self._print_target, self.debug_level, 
                "Starting PapermillHandler run...", DEBUG_INFO)
        else:
            msg = "Repeated calls to start have no effect."
            print_debug(self._print_target, self.debug_level, 
                msg, DEBUG_WARNING)
            raise RuntimeWarning(msg)

    def stop(self)->None:
        if self._worker is None:
            msg = "Cannot stop thread that is not started."
            print_debug(self._print_target, self.debug_level, 
                msg, DEBUG_WARNING)
            raise RuntimeWarning(msg)
        else:
            self._stop_pipe[1].send(1)
            self._worker.join()
        print_debug(self._print_target, self.debug_level, 
            "Worker thread stopped", DEBUG_INFO)

    def handle(self, event:FileSystemEvent, rule:BaseRule)->None:
        # TODO finish implementation and test

        print_debug(self._print_target, self.debug_level, 
            f"Handling event {event.src_path}", DEBUG_INFO)

        file_hash = get_file_hash(event.src_path, SHA256)   

        yaml_dict = {}
        for var, val in rule.pattern.parameters.items():
            yaml_dict[var] = val
        for var, val in rule.pattern.outputs.items():
            yaml_dict[var] = val
        yaml_dict[rule.pattern.triggering_file] = event.src_path

        if not rule.pattern.sweep:
            waiting_for_threaded_resources = True
            while waiting_for_threaded_resources:
                try:
                    worker = threading.Thread(
                        target=self.execute_job,
                        args=[event, rule, yaml_dict, file_hash])
                    worker.daemon = True
                    worker.start()
                    waiting_for_threaded_resources = False
                except threading.ThreadError:
                    sleep(1)
        else:
            for var, val in rule.pattern.sweep.items():
                values = []

                par_val = rule.pattern.sweep[SWEEP_START]
                while par_val <= rule.pattern.sweep[SWEEP_STOP]:
                    values.append(par_val)
                    par_val += rule.pattern.sweep[SWEEP_JUMP]

                for value in values:
                    yaml_dict[var] = value
                    waiting_for_threaded_resources = True
                    while waiting_for_threaded_resources:
                        try:
                            worker = threading.Thread(
                                target=self.execute_job,
                                args=[event, rule, yaml_dict, file_hash])
                            worker.daemon = True
                            worker.start()
                            waiting_for_threaded_resources = False
                        except threading.ThreadError:
                            sleep(1)

    def add_job(self, job):
        self._jobs_lock.acquire()
        try:
            self._jobs.append(job)
        except Exception as e:
            self._jobs_lock.release()
            raise e
        self._jobs_lock.release()

    def get_jobs(self):
        self._jobs_lock.acquire()
        try:
            jobs_deepcopy =  copy.deepcopy(self._jobs)
        except Exception as e:
            self._jobs_lock.release()
            raise e
        self._jobs_lock.release()
        return jobs_deepcopy

    def _is_valid_inputs(self, inputs:list[VALID_CHANNELS])->None:
        valid_list(inputs, VALID_CHANNELS)

    def _is_valid_handler_base(self, handler_base)->None:
        valid_existing_dir_path(handler_base)

    def _is_valid_output_dir(self, output_dir)->None:
        valid_existing_dir_path(output_dir, allow_base=True)

    def execute_job(self, event:FileSystemEvent, rule:BaseRule, 
            yaml_dict:dict[str,Any], triggerfile_hash:str)->None:

        job_dict = {
            JOB_ID: generate_id(prefix="job_", existing_ids=self.get_jobs()),
            JOB_PATTERN: rule.pattern,
            JOB_RECIPE: rule.recipe,
            JOB_RULE: rule.name,
            JOB_PATH: event.src_path,
            JOB_HASH: triggerfile_hash,
            JOB_STATUS: STATUS_QUEUED,
            JOB_CREATE_TIME: datetime.now(),
            JOB_REQUIREMENTS: rule.recipe.requirements
        }

        print_debug(self._print_target, self.debug_level, 
            f"Creating job for event at {event.src_path} with ID "
            f"{job_dict[JOB_ID]}", DEBUG_INFO)

        self.add_job(job_dict[JOB_ID])

        yaml_dict = self.replace_keywords(
            yaml_dict,
            job_dict[JOB_ID],
            event.src_path,
            event.monitor_base
        )

        job_dir = os.path.join(self.handler_base, job_dict[JOB_ID])
        make_dir(job_dir)

        meta_file = os.path.join(job_dir, META_FILE)
        write_yaml(job_dict, meta_file)

        base_file = os.path.join(job_dir, BASE_FILE)
        write_notebook(rule.recipe.recipe, base_file)

        param_file = os.path.join(job_dir, PARAMS_FILE)
        write_yaml(yaml_dict, param_file)

        job_file = os.path.join(job_dir, JOB_FILE)
        result_file = os.path.join(job_dir, RESULT_FILE)

        job_dict[JOB_STATUS] = STATUS_RUNNING
        job_dict[JOB_START_TIME] = datetime.now()

        write_yaml(job_dict, meta_file)

        if JOB_HASH in job_dict:
            triggerfile_hash = get_file_hash(job_dict[JOB_PATH], SHA256)
            if not triggerfile_hash \
                    or triggerfile_hash != job_dict[JOB_HASH]:
                job_dict[JOB_STATUS] = STATUS_SKIPPED
                job_dict[JOB_END_TIME] = datetime.now()
                msg = "Job was skipped as triggering file " + \
                    f"'{job_dict[JOB_PATH]}' has been modified since " + \
                    "scheduling. Was expected to have hash " + \
                    f"'{job_dict[JOB_HASH]}' but has '{triggerfile_hash}'."
                job_dict[JOB_ERROR] = msg
                write_yaml(job_dict, meta_file)
                print_debug(self._print_target, self.debug_level, 
                    msg, DEBUG_ERROR)
                return

        try:
            job_notebook = parameterize_jupyter_notebook(
                rule.recipe.recipe, yaml_dict
            )
            write_notebook(job_notebook, job_file)
        except Exception:
            job_dict[JOB_STATUS] = STATUS_FAILED
            job_dict[JOB_END_TIME] = datetime.now()
            msg = f"Job file {job_dict[JOB_ID]} was not created successfully"
            job_dict[JOB_ERROR] = msg
            write_yaml(job_dict, meta_file)
            print_debug(self._print_target, self.debug_level, 
                msg, DEBUG_ERROR)
            return

        try:
            papermill.execute_notebook(job_file, result_file, {})
        except Exception:
            job_dict[JOB_STATUS] = STATUS_FAILED
            job_dict[JOB_END_TIME] = datetime.now()
            msg = 'Result file %s was not created successfully'
            job_dict[JOB_ERROR] = msg
            write_yaml(job_dict, meta_file)
            print_debug(self._print_target, self.debug_level, 
                msg, DEBUG_ERROR)
            return

        job_dict[JOB_STATUS] = STATUS_DONE
        job_dict[JOB_END_TIME] = datetime.now()
        write_yaml(job_dict, meta_file)

        job_output_dir = os.path.join(self.output_dir, job_dict[JOB_ID])

        shutil.move(job_dir, job_output_dir)

        print_debug(self._print_target, self.debug_level, 
            f"Completed job {job_dict[JOB_ID]} with output at "
            f"{job_output_dir}", DEBUG_INFO)

        return

    def replace_keywords(self, old_dict:dict[str,str], job_id:str, 
            src_path:str, monitor_base:str)->dict[str,str]:
        new_dict = {}

        filename = os.path.basename(src_path)
        dirname = os.path.dirname(src_path)
        relpath = os.path.relpath(src_path, monitor_base)
        reldirname = os.path.dirname(relpath)
        (prefix, extension) = os.path.splitext(filename)

        for var, val in old_dict.items():
            if isinstance(val, str):
                val = val.replace(KEYWORD_PATH, src_path)
                val = val.replace(KEYWORD_REL_PATH, relpath)
                val = val.replace(KEYWORD_DIR, dirname)
                val = val.replace(KEYWORD_REL_DIR, reldirname)
                val = val.replace(KEYWORD_FILENAME, filename)
                val = val.replace(KEYWORD_PREFIX, prefix)
                val = val.replace(KEYWORD_BASE, monitor_base)
                val = val.replace(KEYWORD_EXTENSION, extension)
                val = val.replace(KEYWORD_JOB, job_id)

                new_dict[var] = val
            else:
                new_dict[var] = val

        return new_dict
