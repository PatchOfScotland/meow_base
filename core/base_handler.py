
"""
This file contains the base MEOW handler defintion. This should be inherited 
from for all handler instances.

Author(s): David Marchant
"""

import os
import stat

from threading import Event, Thread
from typing import Any, Tuple, Dict, Union
from time import sleep

from meow_base.core.vars import VALID_CHANNELS, EVENT_RULE, EVENT_PATH, \
    VALID_HANDLER_NAME_CHARS, META_FILE, JOB_ID, JOB_FILE, JOB_PARAMETERS, \
    DEFAULT_JOB_QUEUE_DIR ,get_drt_imp_msg
from meow_base.core.meow import valid_event
from meow_base.patterns.file_event_pattern import WATCHDOG_HASH
from meow_base.functionality.file_io import threadsafe_write_status, \
    threadsafe_update_status, make_dir, write_file, lines_to_string
from meow_base.functionality.validation import check_implementation, \
    valid_string, valid_natural, valid_dir_path
from meow_base.functionality.meow import create_job_metadata_dict, \
    replace_keywords
from meow_base.functionality.naming import generate_handler_id

class BaseHandler:
    # An identifier for a handler within the runner. Can be manually set in 
    # the constructor, or autogenerated if no name provided.
    name:str
    # A channel for sending messages to the runner event queue. Note that this 
    # will be overridden by a MeowRunner, if a handler instance is passed to 
    # it, and so does not need to be initialised within the handler itself, 
    # unless the handler is running independently of a runner.
    to_runner_event: VALID_CHANNELS
    # A channel for sending messages to the runner job queue. Note that this 
    # will be overridden by a MeowRunner, if a handler instance is passed to 
    # it, and so does not need to be initialised within the handler itself, 
    # unless the handler is running independently of a runner.
    to_runner_job: VALID_CHANNELS    
    # Directory where queued jobs are initially written to. Note that this 
    # will be overridden by a MeowRunner, if a handler instance is passed to 
    # it, and so does not need to be initialised within the handler itself.
    job_queue_dir:str
    # A count, for how long a handler will wait if told that there are no 
    # events in the runner, before polling again. Default is 5 seconds.
    pause_time: int
    def __init__(self, name:str='', job_queue_dir:str=DEFAULT_JOB_QUEUE_DIR, 
            pause_time:int=5)->None:
        """BaseHandler Constructor. This will check that any class inheriting 
        from it implements its validation functions."""
        check_implementation(type(self).valid_handle_criteria, BaseHandler)
        check_implementation(type(self).get_created_job_type, BaseHandler)
        check_implementation(type(self).create_job_recipe_file, BaseHandler)
        if not name:
            name = generate_handler_id()
        self._is_valid_name(name)
        self.name = name
        self._is_valid_job_queue_dir(job_queue_dir)
        self.job_queue_dir = job_queue_dir
        self._is_valid_pause_time(pause_time)
        self.pause_time = pause_time

    def __new__(cls, *args, **kwargs):
        """A check that this base class is not instantiated itself, only 
        inherited from"""
        if cls is BaseHandler:
            msg = get_drt_imp_msg(BaseHandler)
            raise TypeError(msg)
        return object.__new__(cls)

    def _is_valid_name(self, name:str)->None:
        """Validation check for 'name' variable from main constructor. Is 
        automatically called during initialisation. This does not need to be 
        overridden by child classes."""
        valid_string(name, VALID_HANDLER_NAME_CHARS)

    def _is_valid_pause_time(self, pause_time:int)->None:
        """Validation check for 'pause_time' variable from main constructor. Is 
        automatically called during initialisation. This does not need to be 
        overridden by child classes."""
        valid_natural(pause_time, hint="BaseHandler.pause_time")

    def _is_valid_job_queue_dir(self, job_queue_dir)->None:
        """Validation check for 'job_queue_dir' variable from main 
        constructor."""
        valid_dir_path(job_queue_dir, must_exist=False)
        if not os.path.exists(job_queue_dir):
            make_dir(job_queue_dir)

    def prompt_runner_for_event(self)->Union[Dict[str,Any],Any]:
        self.to_runner_event.send(1)

        if self.to_runner_event.poll(self.pause_time):
            return self.to_runner_event.recv()
        return None

    def send_job_to_runner(self, job_id:str)->None:
        self.to_runner_job.send(job_id)

    def start(self)->None:
        """Function to start the handler as an ongoing thread, as defined by 
        the main_loop function. Together, these will execute any code in a 
        implemented handlers handle function sequentially, but concurrently to 
        any other handlers running or other runner operations. This is intended 
        as a naive mmultiprocessing implementation, and any more in depth 
        parallelisation of execution must be implemented by a user by 
        overriding this function, and the stop function."""
        self._stop_event = Event()        
        self._handle_thread = Thread(
            target=self.main_loop, 
            args=(self._stop_event,),
            daemon=True,
            name="handler_thread"
        )
        self._handle_thread.start()

    def stop(self)->None:
        """Function to stop the handler as an ongoing thread. May be overidden 
        by any child class. This function should also be overriden if the start
        function has been."""

        self._stop_event.set()
        self._handle_thread.join()
        
    def main_loop(self, stop_event)->None:
        """Function defining an ongoing thread, as started by the start 
        function and stoped by the stop function. """

        while not stop_event.is_set():
            reply = self.prompt_runner_for_event()

            # If we have recieved 'None' then we have already timed out so skip 
            # this loop and start again
            if reply is None:
                continue

            try:
                valid_event(reply)
            except Exception as e:
                # Were not given an event, so sleep before trying again
                sleep(self.pause_time)


            try:
                self.handle(reply)
            except Exception as e:
                # TODO some error reporting here
                pass

    def valid_handle_criteria(self, event:Dict[str,Any])->Tuple[bool,str]:
        """Function to determine given an event defintion, if this handler can 
        process it or not. Must be implemented by any child process."""
        pass

    def handle(self, event:Dict[str,Any])->None:
        """Function to handle a given event. May be overridden by any child 
        process. Note that once any handling has occured, the 
        send_job_to_runner function should be called to inform the runner of 
        any resultant jobs."""
        rule = event[EVENT_RULE]

        # Assemble job parameters dict from pattern variables
        params = rule.pattern.assemble_params_dict(event)

        if isinstance(params, list):
            for param in params:
                self.setup_job(event, param)
        else:
            self.setup_job(event, params)

    def setup_job(self, event:Dict[str,Any], params_dict:Dict[str,Any])->None:
        """Function to set up new job dict and send it to the runner to be 
        executed."""

        # Get base job metadata
        meow_job = self.create_job_metadata_dict(event, params_dict)

        # Get updated job parameters
        # TODO replace this with generic implementation
        from meow_base.patterns.file_event_pattern import WATCHDOG_BASE
        params_dict = replace_keywords(
            params_dict,
            meow_job[JOB_ID],
            event
        )

        # Create a base job directory
        job_dir = os.path.join(self.job_queue_dir, meow_job[JOB_ID])
        make_dir(job_dir)

        # Create job metadata file
        meta_file = self.create_job_meta_file(job_dir, meow_job)

        # Create job recipe file
        recipe_command = self.create_job_recipe_file(job_dir, event, params_dict)

        # Create job script file
        script_command = self.create_job_script_file(job_dir, recipe_command)

        threadsafe_update_status(
            {
                # TODO make me not tmp variables and update job dict validation
                "tmp recipe command": recipe_command,
                "tmp script command": script_command
            }, 
            meta_file
        )

        # Send job directory, as actual definitons will be read from within it
        self.send_job_to_runner(job_dir)

    def get_created_job_type(self)->str:
        pass # Must implemented

    def create_job_metadata_dict(self, event:Dict[str,Any], 
            params_dict:Dict[str,Any])->Dict[str,Any]:
        return create_job_metadata_dict(
            self.get_created_job_type(), 
            event, 
            extras={
                JOB_PARAMETERS:params_dict
            }
        )

    def create_job_meta_file(self, job_dir:str, meow_job:Dict[str,Any]
            )->Dict[str,Any]:
        meta_file = os.path.join(job_dir, META_FILE)

        threadsafe_write_status(meow_job, meta_file)

        return meta_file

    def create_job_recipe_file(self, job_dir:str, event:Dict[str,Any], params_dict:Dict[str,Any]
            )->str:
        pass # Must implemented

    def create_job_script_file(self, job_dir:str, recipe_command:str)->str:
        # TODO Make this more generic, so only checking hashes if that is present
        job_script = [
            "#!/bin/bash",
            "",
            "# Get job params",
            f"given_hash=$(grep '{WATCHDOG_HASH}: *' $(dirname $0)/job.yml | tail -n1 | cut -c 14-)",
            f"event_path=$(grep '{EVENT_PATH}: *' $(dirname $0)/job.yml | tail -n1 | cut -c 15-)",
            "",
            "echo event_path: $event_path",
            "echo given_hash: $given_hash",
            "",
            "# Check hash of input file to avoid race conditions",
            "actual_hash=$(sha256sum $event_path | cut -c -64)",
            "echo actual_hash: $actual_hash",
            "if [ $given_hash != $actual_hash ]; then",
            "   echo Job was skipped as triggering file has been modified since scheduling",
            "   exit 134",
            "fi",
            "",
            "# Call actual job script",
            recipe_command,
            "",
            "exit $?"
        ]
        job_file = os.path.join(job_dir, JOB_FILE)
        write_file(lines_to_string(job_script), job_file)
        os.chmod(job_file, stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH | stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH )

        return os.path.join(".", JOB_FILE)