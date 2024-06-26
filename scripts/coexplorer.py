

#############################################################################################################
# TODO: - Create separate thread for training so state transition time is exact
# TODO: - Duplicate code for exploring_starts and random_action functions (pseudo-count/prediction gain calculation)
#############################################################################################################
import os
import shutil
import sys
import time
import copy
import pickle
import random
import numpy as np
from argparse import ArgumentParser
import tensorflow.compat.v1 as tf
tf.disable_v2_behavior()

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2' 

from agent import DTAMERAgent, Memory
from tracker import Tracker
from environment import Env
from OSCinterface import OSCClass

# TRAINING_PARAMS = [STATES, STEPS, HL_NB, HL_SIZE, EPS_DEC, LR, REWARD_LEN, REWARD, REPLAY_SIZE, BATCH_SIZE, EPS_START]
# TRAINING_PARAMS_1 = [16, 1, 2, 100, 0, 0.001, 4, 1, 0, 4, 0.5]
# TRAINING_PARAMS_1 = [1, 100, 2, 100, 2000, 0.002, 10, 1, 700, 32, 0.1]

# TRAINING_PARAMS_1 = [     
#                         10,     #STATES #can be changed with script arg
#                         100,    #STEPS
#                         2,      #HL_NB
#                         100,    #HL_SIZE
#                         2000,   #EPS_DEC
#                         0.002,  #LR
#                         10,     #REWARD_LEN
#                         1,      #REWARD
#                         700,    #REPLAY_SIZE 700
#                         32,     #BATCH_SIZE
#                         0.3     #EPS_START default : 0.1
#                     ]


#TRAINING_LABEL = 'TEST'

TRANSITION_TIME = 1 # modified for tréma 
MAX_TRANSITION_TIME = 1 #not used

MAX_REWARD_LENGTH = 64 
MAX_STATE_STEPS = 100
PRINT_FREQ = 250

# TRAINING = TRAINING_PARAMS_1
# STATE_SIZE = TRAINING[0]
# ACTION_SIZE = 2 * STATE_SIZE
# STATE_STEPS = TRAINING[1]
# HIDDEN_LAYER_NB = TRAINING[2]
# HIDDEN_LAYER_SIZE = TRAINING[3]
# EPS_DECAY = TRAINING[4]
# LEARNING_RATE = TRAINING[5]
# REWARD_LENGTH = TRAINING[6]
# REWARD = TRAINING[7]
# REPLAY_SIZE = TRAINING[8]
# BATCH_SIZE = TRAINING[9]
# EPS_START = TRAINING[10]

def debug( message ):
    print(message)
    osc_interface.client.send_message("/debug", message)

def init_program(started_bool = False):
    global save_path
    
    tf.compat.v1.reset_default_graph()
    sess = tf.compat.v1.Session()

    agent = DTAMERAgent(STATE_SIZE, ACTION_SIZE, HIDDEN_LAYER_NB, HIDDEN_LAYER_SIZE, EPS_DECAY, LEARNING_RATE, REWARD_LENGTH, REWARD, TRANSITION_TIME, REPLAY_SIZE, BATCH_SIZE, EPS_START)
    env = Env(STATE_SIZE, STATE_STEPS, REWARD_LENGTH, REWARD)
    tracker = Tracker(STATE_SIZE, MAX_STATE_STEPS, TRAINING_LABEL)

    log_path = r'./models/' + TRAINING_LABEL

    # if not started_bool and os.path.isdir(log_path):
    #     debug('Training label already exist. Deleting old folder')
    #     shutil.rmtree(log_path)


    if not os.path.isdir(log_path):
        debug('creating model directory')
        debug(log_path)
        os.makedirs(log_path)

    sess.run(tf.global_variables_initializer())
    
    save_path = log_path
    debug("Model save path is : " + os.path.abspath(log_path))
    debug('State steps|increment = ' + str(env.state_steps) + '|' + str(1.0 / env.state_steps))

    return sess, agent, env, tracker

def resample_actions(env, t, resample_factor):
    print(resample_factor)
    state_steps = int(max(2,min(env.state_steps * resample_factor,MAX_STATE_STEPS)))
    
    env.state_steps = state_steps
    debug('time; ' + str(t) + '; Resample! Increment = ' + str(1.0 / state_steps))

def adjust_reward_length(agent, t, reward_length_factor):

    #new_reward_length = int(max(1,min(agent.reward_length * reward_length_factor,MAX_REWARD_LENGTH)))
    agent.reward_length = int(max(1,min(agent.reward_length + reward_length_factor,MAX_REWARD_LENGTH)))
    env.reward_length = agent.reward_length

    temp_memory = copy.deepcopy(agent.reward_memory)
    temp_memory2 = copy.deepcopy(agent.delay_memory)

    agent.reward_memory = Memory(agent.reward_length, agent.state_size)
    agent.delay_memory = Memory(int(np.ceil(0.2 / agent.transition_time + agent.reward_length)), agent.state_size)

    agent.reward_memory.buffer.extend(temp_memory.buffer)
    agent.delay_memory.buffer.extend(temp_memory2.buffer)

    debug('time; ' + str(t) + '; New reward length! Reward length = ' + str(agent.reward_length))

def rescale_transitions(agent, t):
    global TRANSITION_TIME

    #TRANSITION_TIME = max(0.015625,min(TRANSITION_TIME * trans_time,MAX_TRANSITION_TIME))
    TRANSITION_TIME = 2/agent.reward_length
    agent.transition_time = TRANSITION_TIME

    temp_memory2 = copy.deepcopy(agent.delay_memory)
    agent.delay_memory = Memory(int(np.ceil(0.2 / agent.transition_time + agent.reward_length)), agent.state_size)
    agent.delay_memory.buffer.extend(temp_memory2.buffer)

    debug('time;' + str(t) + '; New transition time! Transition time = ' + str(TRANSITION_TIME))

def explore_state(sess, agent, env, tracker, t, osc_interface):

    state = 0
    prediction_gain = -10
    next_density = copy.deepcopy(agent.density_weights)
    
    for i in range(agent.state_size*4):
        state_nxt = env.reset_random()
        tiles_idx = agent.calc_tiles_idx(state_nxt[0])
        state_prob_nxt = np.sum(agent.density_weights[tiles_idx])/((t+1) * agent.numtilings)

        next_density[tiles_idx] += 1
        next_state_prob_nxt = np.sum(next_density[tiles_idx]) / ((t+2) * agent.numtilings)
        next_density[tiles_idx] -= 1

        prediction_gain_nxt = np.log(next_state_prob_nxt) - np.log(state_prob_nxt)

        if prediction_gain_nxt > prediction_gain:
            prediction_gain = copy.deepcopy(prediction_gain_nxt)
            state = copy.deepcopy(state_nxt)

    debug('time; ' + str(t) + '; Explore from new state! : ' + str(state))
    
    tracker.fill_trajectory(state,'Explore_state')
    osc_interface.send_zone(state, 'Explore_state')
    action, rand_bool = agent.act(sess, state)

    # timeout_start = time.time()
    # reward_idx = 1

    osc_interface.send_state(state[0])

    ##make function to toggle distribution of reward on runtime vvv

    # Following code added to assure reward is distributed over appropriate reward_length (ex. When explore_state
    # and then assigning reward, needs to be distributed from explore_state onwards -> variable reward_length size)
    # reward = 0
    # if not osc_interface.paused:
    #     while time.time() < (timeout_start + (agent.reward_length * TRANSITION_TIME)):
    #         next_state = env.step(state, action)
    #         next_action, rand_bool = agent.act(sess, next_state, t)
    #         agent.remember_transition(state, action)
    #         osc_interface.client.send_message('/params', state[0])
    #
    #
    #         state = next_state
    #         action = next_action
    #
    #         while time.time() < (timeout_start + (reward_idx * TRANSITION_TIME)):
    #             reward = osc_interface.reward
    #             osc_interface.client.send_message('/reward_in', reward)
    #
    #         osc_interface.send_zone(state, reward)
    #
    #         reward = 0
    #         osc_interface.reward = 0
    #         reward_idx += 1
    #         t += 1
    #
    #     reward = osc_interface.reward
    #     osc_interface.reward = 0
    #     osc_interface.received = False
    #     rewards = env.set_reward(reward)
    #
    #     if not reward == 0:
    #         tracker.fill_trajectory(state, reward)
    #         agent.remember_rewards(rewards)

    return state, action, t

def explore_action(agent, state, t):
    action = 999
    prediction_gain = -10
    #next_density = copy.deepcopy(agent.density_weights)
    invalid_actions = [ind * 2 + 1 if x == 0 else ind * 2 for ind, x in enumerate(state[0]) if x in (0, 1)]

    for i in range(agent.state_size * 2):
        test_state = env.step(state, i)
        tiles_idx = agent.calc_tiles_idx(test_state[0])
        test_state_prob = np.sum(agent.density_weights[tiles_idx]) / ((t + 1) * agent.numtilings + 1)

        agent.density_weights[tiles_idx] += 1
        test_state_prob_nxt = np.sum(agent.density_weights[tiles_idx]) / ((t + 2) * agent.numtilings + 1)
        agent.density_weights[tiles_idx] -= 1

        prediction_gain_nxt = np.log(test_state_prob_nxt) - np.log(test_state_prob)

        if prediction_gain_nxt > prediction_gain and i not in invalid_actions:
            prediction_gain = copy.deepcopy(prediction_gain_nxt)
            action = i

    debug('time; ' + str(t) + '; Explore new states! : ' + str(state))

    return action

def explore_random_action(agent, state, t):
    action = 999
    invalid_actions = [ind * 2 + 1 if x == 0 else ind * 2 for ind, x in enumerate(state[0]) if x in (0, 1)]

    i = random.choice(range(agent.state_size * 2))

    while i in invalid_actions:
        i = random.choice(range(agent.state_size * 2))
    else:
        action = i

    debug('time; ' + str(t) + '; Explore random action! : ' + str(state))

    return action

def zone_feedback(agent, env, tracker, state, score): #throw a bug whe superlike

    if osc_interface.paused:
        start_state = copy.deepcopy(state)
        print(start_state)
    else:
        start_state = copy.deepcopy(agent.delay_memory.sample(1))[0][0]

    super_like_size = agent.reward_length

    temp_state = copy.deepcopy(start_state)

    for i in range(agent.state_size):
        action = i * 2
        for j in range(2):
            for k in range(max(1,int(super_like_size/2))):
                if not (temp_state[0][i] == 1 and ((action + j) % 2) == 0) and not (temp_state[0][i] == 0 and
                                                                                    ((action + j) % 2) == 1):
                    next_state = env.step(temp_state, action + j)
                    agent.reward_memory.add(np.array([(temp_state, action + j, - 2 * score * agent.reward_size)],dtype=object))
                    agent.reward_memory.add(np.array([(next_state, action - j + 1, 2 * score * agent.reward_size)],dtype=object))
                    temp_state = next_state
            if len(agent.reward_memory.buffer) == agent.reward_length: # Bugfix: To prevent superlike after
                                                                # adjust_reward_length with state[0]=1
                batch = np.reshape(agent.reward_memory.buffer, [agent.reward_length, 3])
                agent.train(sess, batch)
            temp_state = start_state
            agent.replay_memory.add(agent.reward_memory.buffer)

    if score == 1:
        debug('Good Zone for ' + str(start_state))
        tracker.fill_trajectory(start_state, 'Superlike')
        osc_interface.send_zone(state, 'Superlike')
    elif score == -1:
        debug('Bad Zone for ' + str(start_state))
        tracker.fill_trajectory(start_state, 'Superdislike')
        osc_interface.send_zone(state, 'Superdislike')

## SCRIPT ARGUMENT PARSING

if __name__ == "__main__":
    parser = ArgumentParser(description='A simple argument input example')
    parser.add_argument("-n", "--name", help="model name", required=True)
    parser.add_argument("-s", "--state", help="number of dimension", required=True )

    
    parser.add_argument( "--steps", default= 10 )
    parser.add_argument("--hl_nb", default= 2 )
    parser.add_argument("--hl_size", default= 100)
    parser.add_argument("--eps_decay",default= 2000)
    parser.add_argument("--learning_rate", default=0.002 )
    parser.add_argument("--reward_length", default=10 )
    parser.add_argument("--reward", default=1)
    parser.add_argument("--replay_size",default= 700)
    parser.add_argument("--batch_size", default=32 )
    parser.add_argument("--eps_start", default= 0.3)

    args = parser.parse_args()
    
    ## TRAINING PARAMETER ATTRIBUTION
    TRAINING_LABEL = args.name
    STATE_SIZE = int(args.state)
    ACTION_SIZE = 2 * int(args.state) #need to recalculate action size after state_size changed

    STATE_STEPS = int(args.steps)
    HIDDEN_LAYER_NB = int(args.hl_nb)
    HIDDEN_LAYER_SIZE = int(args.hl_size)
    EPS_DECAY = int(args.eps_decay)
    LEARNING_RATE = float(args.learning_rate)
    REWARD_LENGTH = int(args.reward_length)
    REWARD = int(args.reward)
    REPLAY_SIZE = int(args.replay_size)
    BATCH_SIZE = int(args.batch_size)
    EPS_START = float(args.eps_start)


    ##OSC INTERFACE INITIALISATION
    osc_interface = OSCClass(STATE_SIZE, ACTION_SIZE, TRANSITION_TIME, "127.0.0.1", 5005, TRAINING_LABEL)
    
    debug("OSC interface initialized") 
    debug("Training label is : " + TRAINING_LABEL)


    #INITIALIZE AGENT AND ENVIRONMENT
    sess, agent, env, tracker = init_program(started_bool = False)
    debug("Session, agent, environment and tracker initialized")

    # RESET VARIABLE TO INITIAL STATE
    reward = 0
    t_idx = 0
    nb_iter = 0
    rewards = np.zeros(agent.reward_length)
    
    state = env.reset()
    
    action, rand_bool = agent.act(sess, state)
    debug("State, action and variable initialized")

    #INITIALISATION DONE
    # First loop, wait here until user starts interaction
    debug("Load model or start session")
    osc_interface.send_workflow_control(init=1)
    
    while osc_interface.paused and osc_interface.running:
        time.sleep(0.01)
        
        
        if osc_interface.load:
            debug("Loading model {}".format( osc_interface.load_modelname))
            agent.load_model(sess, osc_interface.load_modelname)
            osc_interface.load = False
    

    osc_interface.send_workflow_control(paused = 0)
    osc_interface.send_state(state[0])
    osc_interface.VSTsample_bool = False

    # Outer loop
    while osc_interface.running:
        ########################################################
        ##############      RL CYCLE         ###################
        ########################################################
        osc_interface.client.send_message("/timeIndex", t_idx)
        
        #print('action')
        #print(action)
        next_state = env.step(state, action)
        next_action, rand_bool = agent.act(sess, next_state, t_idx)
        agent.remember_transition(state, action)

        osc_interface.send_state(next_state[0])
        osc_interface.send_workflow_control(rand = rand_bool) ##verify what this does in max patch

        # Inner loop, get reward during or after transition
        timeout_start = time.time()
        
        while time.time() < (timeout_start + TRANSITION_TIME):
            reward = osc_interface.reward
            osc_interface.send_agent_control(reward_in = reward)
           

        # Collect tracking data
        tracker.fill_trajectory(state, reward)
        osc_interface.send_zone(state, reward)

        # Prepare next cycle
        state = next_state
        action = next_action
        t_idx += 1

        ########################################################
        ##############      TRAIN MODEL      ###################
        ########################################################
        # Train on feedback + exploration_bonus
        if osc_interface.received and len(agent.delay_memory.buffer) >= agent.reward_length:
            osc_interface.reward = 0
            osc_interface.received = False
            rewards = env.set_reward(reward)
            debug(str(state) + '; eps = ' + str(agent.eps_threshold))

            agent.remember_rewards(rewards)
            batch = np.reshape(agent.reward_memory.buffer, [agent.reward_length, 3])
            agent.train(sess, batch)

            reward = 0
            rewards *= 0

        # Train on experience (replay memory contains only feedback WITHOUT bonus)
        elif len(agent.replay_memory.buffer) > (2*agent.batch_size):
            batch = agent.replay_memory.sample_random(agent.batch_size)
            #debug("Train on experience")
            agent.train(sess, batch)

        # Train on exploration_bonus
        elif len(agent.delay_memory.buffer) >= agent.reward_length:
            batch = agent.delay_memory.sample(agent.reward_length)
            batch = np.reshape(batch, [agent.reward_length, 3])
            #debug("Train on exploration bonus")
            agent.train(sess, batch)

        ########################################################
        ##############          PAUSED       ###################
        ########################################################
        if osc_interface.paused:

            osc_interface.send_workflow_control(paused = 1)

            while osc_interface.paused:
                time.sleep(0.01)

                #maybe previous state
                if osc_interface.previous:
                    osc_interface.previous = False
                    if not len(tracker.trajectory) == (abs(osc_interface.idx)-1):
                        osc_interface.idx += 1
                        state = tracker.trajectory[-osc_interface.idx][1].T
                        action, _ = agent.act(sess, state, t_idx)

                        osc_interface.send_agent_control(previous_s = 1)
                        osc_interface.send_state(state[0])
                
                #maybe next state
                if osc_interface.next:
                    osc_interface.debug("Next state")
                    osc_interface.next = False
                    if not osc_interface.idx == 1:
                    
                        osc_interface.idx -= 1
                        state = tracker.trajectory[-osc_interface.idx][1].T
                        action, _ = agent.act(sess, state, t_idx)

                        osc_interface.send_agent_control(next_s = 1)
                        osc_interface.send_state(state[0])
                
                #maybe set state
                if osc_interface.VSTsample_bool: ##set state to vst state
                    
                    state = osc_interface.VSTstate
                    
                    state = np.reshape(state,[1,agent.state_size])
                    osc_interface.send_state(state[0])
                    action, _ = agent.act(sess, state, t_idx)
                    osc_interface.VSTsample_bool = False

                # Provide one-state reward
                #maybe received reward
                if osc_interface.received:
                    reward = copy.deepcopy(osc_interface.reward)
                    osc_interface.reward = 0
                    osc_interface.received = False

                    agent.remember_single_reward(tracker, state, action, reward)
                    agent.train(sess, np.reshape(np.array([state,action,reward], dtype=object), [1, 3]))

                    next_state = env.step(state, action)
                    next_action, rand_bool = agent.act(sess, next_state, t_idx)
                    agent.remember_transition(state, action)

                    osc_interface.send_state(next_state[0])
                    osc_interface.send_workflow_control(rand=rand_bool)
                    osc_interface.send_agent_control(reward_in=reward)
                    osc_interface.send_zone(state, reward)
                    debug('one state reward')
                    debug(str(reward) + ' for action ' + str(action) + ' and state ' + str(state))

                    state = next_state
                    action = next_action
                    reward = 0
                    t_idx += 1

                
                #maybe reset state
                if osc_interface.resetstate: # Control 1: Explore state
                    osc_interface.resetstate = False
                    debug('reset state')
                    osc_interface.send_agent_control(explore_state = 1)
                    state, action , t_idx = explore_state(sess, agent, env, tracker, t_idx, osc_interface)

               #maybe zone feedback
                if osc_interface.super_like:  # Control 4: Zone feedback
                    print('zone feedback while paused')
                    osc_interface.super_like = False
                    osc_interface.send_agent_control(superlike=osc_interface.superlike_value)
                    state = osc_interface.VSTstate
                    print(state)
                    state = np.reshape(state, [1, agent.state_size])
                    zone_feedback(agent, env, tracker, state, osc_interface.superlike_value)

               #maybe explore random action
                if osc_interface.rnd_action:  # Control 5: Explore random action
                    osc_interface.rnd_action = False
                    debug("Explore random action")
                    osc_interface.send_agent_control(explore_action=1)
                    action = explore_random_action(agent, state, t_idx)
                    state = env.step(state, action)
                    osc_interface.send_state(state[0])

                #maybe reset model
                if osc_interface.resetmodel: #duplicate? # Control 6: reset model
                    debug('Reset model')
                    osc_interface.initialise_client(STATE_SIZE, ACTION_SIZE, TRANSITION_TIME, 1)
                    if not TRAINING_LABEL == 'TEST':
                        agent.save_model(sess, save_path, 'model_reset', t_idx)
                        with open('./datalogs/tracker_nb' + str(nb_iter) + '_it' + str(t_idx) + '_reset_' + TRAINING_LABEL + '.pkl', 'wb') as output:
                            pickle.dump(tracker, output, pickle.HIGHEST_PROTOCOL)
                            nb_iter += 1
                    sess, agent, env, tracker = init_program(started_bool = True)
                    osc_interface.resetmodel = False

                #maybe save model
                if osc_interface.save:
                    debug('Saving model')
                    
                    agent.save_model(sess, save_path,osc_interface.save_modelname, t_idx)
                    osc_interface.save = False

                #maybe load model
                if osc_interface.load:
                    agent.load_model(sess, osc_interface.load_modelname)
                    osc_interface.load = False

                if not osc_interface.running:
                    break

            #after unpausing        
            osc_interface.resetstate = False
            osc_interface.resample_states = False
            osc_interface.new_speed = False
            osc_interface.super_like = False
            osc_interface.rnd_action = False
            osc_interface.idx = 1
            osc_interface.send_workflow_control(paused = 0)


        
        ########################################################
        ##############    AGENT CONTROLS     ###################
        ########################################################
        
        #maybe explore state
        if osc_interface.resetstate:  # Control 1: Explore state
            osc_interface.resetstate = False
            osc_interface.send_agent_control(explore_state = 1)
            state, action, t_idx = explore_state(sess, agent, env, tracker, t_idx, osc_interface)

        #maybe adjust precision
        if osc_interface.resample_states: # Control 2: Adjust precision (Rescale actions)
            osc_interface.resample_states = False
            osc_interface.send_agent_control(precision=1 / env.state_steps)
            resample_actions(env, t_idx, osc_interface.resample_factor)

        # Control 3: Adjust speed
        # - Adjust reward length
        # - Set new transition time
        if osc_interface.new_speed:
            osc_interface.new_speed = False

            print("Changing speed",osc_interface.increment_reward_length )

            osc_interface.send_agent_control(time = (TRANSITION_TIME*1000))

            adjust_reward_length(agent, t_idx, osc_interface.increment_reward_length)
            rescale_transitions(agent, t_idx)

        #maybe zone feedback
        if osc_interface.super_like: # Control 4: Super (dis)like
            osc_interface.super_like = False
            osc_interface.send_agent_control(superlike = osc_interface.superlike_value)

            osc_interface.send_state(agent.delay_memory.sample(1)[0][0][0])
            zone_feedback(agent, env, tracker, state, osc_interface.superlike_value)

        #maybe explore actiom
        if osc_interface.rnd_action:  # Control 5: Explore action
            print('random_action')
            osc_interface.rnd_action = False
            osc_interface.send_agent_control(explore_action = 1)
            action = explore_action(agent, state, t_idx)

        # Control 6: reset model
        if osc_interface.resetmodel:
            osc_interface.initialise_client(STATE_SIZE, ACTION_SIZE, TRANSITION_TIME, 1)
            if not TRAINING_LABEL == 'TEST':
                agent.save_model(sess, save_path, 'model_reset', t_idx)
                with open('./datalogs/tracker_nb' + str(nb_iter) + '_it' + str(t_idx) + '_reset_' + TRAINING_LABEL + '.pkl','wb') as output:
                    pickle.dump(tracker, output, pickle.HIGHEST_PROTOCOL)
                    nb_iter += 1
            sess, agent, env, tracker = init_program(started_bool = True)
            osc_interface.resetmodel = False
            osc_interface.paused = True


    # Save model and end program
    osc_interface.initialise_client(STATE_SIZE, ACTION_SIZE , TRANSITION_TIME, 1)
    # if not TRAINING_LABEL == 'TEST':
    #     agent.save_model(sess, save_path, 'model_end', t_idx)
    #     with open('./datalogs/tracker_nb' + str(nb_iter) + '_it' + str(t_idx) + '_end_' + TRAINING_LABEL + '.pkl','wb') as output:
    #         pickle.dump(tracker, output, pickle.HIGHEST_PROTOCOL)
    
    # debug('Data saved at ' + str(os.getcwd()) + '/datalogs/')

    
    osc_interface.end_thread()
    sys.exit()



