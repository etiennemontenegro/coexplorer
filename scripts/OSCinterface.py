from pythonosc import udp_client
from pythonosc import dispatcher
from pythonosc import osc_server
import numpy as np
import threading
import os
class OSCClass:
    def __init__(self, STATE_SIZE, ACTION_SIZE , TRANSITION_TIME, ip, port, TRAINING_LABEL):

        self.received = False
        self.resample_states = False
        self.resetstate = False
        self.new_speed = False
        self.super_like = False
        self.rnd_action = False
        self.previous = False
        self.next = False
        self.VSTsample_bool = False
        self.get_trajlist = False

        self.running = True
        self.paused = True
        self.save = False
        self.load = False
        self.resetmodel = False

        self.reward = 0
        self.resample_factor = 0
        self.superlike_value = 0
        self.increment_reward_length = 0
        self.state_idx = 0
        self.row1_idx = 0
        self.col1_idx = 0
        self.row2_idx = 0
        self.col2_sl_idx = 0
        self.col2_sdl_idx = 0
        self.col2_es_idx = 0
        self.idx = 1
        self.VSTstate = 0
        self.save_modelname = None
        self.save_path = None

        self.client = udp_client.SimpleUDPClient('127.0.0.1', 8000)
        self.initialise_client(STATE_SIZE, ACTION_SIZE , TRANSITION_TIME, 1)

        self.dispatch = dispatcher.Dispatcher()

        # Main controls
        self.dispatch.map("/direction", self.store_reward) #guiding feedback

        # Workflow controls
        self.dispatch.map("/stop", self.stop_program)
        self.dispatch.map("/autoexplore", self.pause_training)  # autonomous mode
        
        self.dispatch.map("/previous_state", self.previous_state) 
        self.dispatch.map("/next_state", self.next_state)
        self.dispatch.map("/sample_vst", self.sample_vststate) #rename preset
        self.dispatch.map("/save", self.save_model)
        self.dispatch.map("/load", self.load_model)
        self.dispatch.map("/reset", self.reset_model)

        # Agent controls
        self.dispatch.map("/resample", self.adjust_sampling)
        self.dispatch.map("/zone", self.record_superlike) #zone feedback
        self.dispatch.map("/explore_state", self.reset_state) #change zone
        self.dispatch.map("/explore_action", self.random_action)
        self.dispatch.map("/speed", self.rescale_reward_length)

        self.server = osc_server.ThreadingOSCUDPServer((ip, port), self.dispatch)
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.start()
        print("OSC Server started")


    
    # ------------------        CLIENT          ------------------------------
    def initialise_client(self, STATE_SIZE, ACTION_SIZE , TRANSITION_TIME, paused_bool):
        self.send_state(np.ones(STATE_SIZE)*0.5)
        self.send_agent_control(time = TRANSITION_TIME * 1000)
        self.send_agent_control(precision = 1.0/ACTION_SIZE)
        self.send_workflow_control(training = 0)
        self.send_workflow_control(paused = paused_bool)
        self.state_idx = 0
        self.row1_idx = 0
        self.col1_idx = 0
        self.row2_idx = 0
        self.col2_sl_idx = 0
        self.col2_sdl_idx = 0
        self.col2_es_idx = 0

    def debug(self, message ):
        print(message)
        self.client.send_message("/debug", message)

    def send_state(self, state):
        self.client.send_message('/state', state)

    ##rename send zone 
    def send_zone(self, state, label): # format osc message to use with jit.cellblock in max patch
        #removed jit.cellblock formatting and sending zone state
        state = str(state[0])[1:-1]
        state_plit = state.split(' ')
        state = list()
    
        for f in state_plit:
            if not f == "":
                state.append(float(f))

        if label == 'Superlike':
            self.client.send_message('/good_zone', state)
        elif label == 'Superdislike':
            self.client.send_message('/bad_zone', state)
        elif label == 'Explore_state':
            self.client.send_message('/explore_state', state)
    
    def send_agent_control(self, **kwargs):
        for key, value in kwargs.items():
            if key == 'reward_in':
                self.client.send_message('/reward_in', value)
            elif key == 'time':
                self.client.send_message('/time', value)
            elif key == 'precision':
                self.client.send_message('/precision', value)
            elif key == 'superlike':
                self.client.send_message('/superlike', self.superlike_value)
            elif key == 'explore_state':
                self.client.send_message('/explore_state', value)
            elif key == 'explore_action':
                self.client.send_message('/explore_action', value)
            elif key == 'previous_s':
                self.client.send_message('/previous_s', value)
            elif key == 'next_s':
                self.client.send_message('/next_s', value)

    def send_workflow_control(self, **kwargs):
        for key, value in kwargs.items():
            if key == 'init':
                self.client.send_message('/init', value) ##use this value to hang program until ready
            elif key == 'paused':
                value = (value + 1) % 2
                self.client.send_message('/paused', value)
            elif key == 'rand':
                self.client.send_message('/rand', value)

    # ------------------        SERVER          ------------------------------
    # ------------------ Basic reward control   ------------------------------
    def store_reward(self,unused_addr, reward):
        self.reward = reward
        self.received = True
        self.debug("Store reward")

    # ------------------ Workflow controls      ------------------------------
    def pause_training(self, unused_addr, pause_bool):
        self.paused = pause_bool

        if pause_bool:
            self.debug("Autonomous exploration off")
        else: 
            self.debug("Autonomous exploration on")

    def save_model(self, unused_addr, *args):
        # self.debug("Save model OSC")
        
        self.save_modelname = args[0]
        print(args[0])
        self.save = True
        self.debug("Save model OSC")


    def load_model(self, unused_addr, model_name):
        self.load_modelname = model_name
        print(model_name)
        self.load = True
        self.debug("Load model")

    def reset_model(self, unused_addr, reset_bool):
        self.resetmodel = True
        self.debug("Reset model")

    def stop_program(self, unused_addr, running_bool):
        self.debug("Stop program")
        self.running = running_bool

    def end_thread(self):
        self.server.shutdown()

    # ------------------ Agent controls         ------------------------------
    def adjust_sampling(self,unused_addr, resample):
        print(resample)
        self.resample_factor = pow(2,resample)
        self.resample_states = True
        self.debug("Adjust sampling")

    #change function name
    def record_superlike(self,unused_addr, superlike_flag):
        self.superlike_value = superlike_flag
        self.super_like = True
        self.debug("record superlike")

    def reset_state(self,unused_addr, reset):
        self.resetstate = True
        self.debug("reset state")

    def random_action(self,unused_addr, action):
        self.rnd_action = True
        self.debug("random action")

    def rescale_reward_length(self, unused_addr, new_reward_length):

        self.debug("changing speed. received value is {}".format(new_reward_length))
        self.increment_reward_length = new_reward_length * -2
        self.debug("increment_reward_length {}".format( self.increment_reward_length))
        self.new_speed = True
        self.debug("rescale reward length")

    ##looks like some controls are only for paused state
    # ------------------ Workflow controls (paused) --------------------------
    def previous_state(self, unused_addr, previous_bool):
        self.previous = True
        self.debug("Previous state")

    def next_state(self, unused_addr, next_bool):
        self.next = True
        #self.debug("Next state")

    def sample_vststate(self, unused_addr, *args): ## save as preset?
        self.debug("sample vst state")
        VSTsample = np.array(args)
        print("vstsample",VSTsample)
        self.VSTstate = VSTsample
        self.VSTsample_bool = True




