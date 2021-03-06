import tensorflow as tf
import numpy as np
import gym


class Environment(object):
    def __init__(self, run_dir, env_name):
        self.name = env_name
        self.gym = gym.make(self.name)
        self.random_initialization = True
        self._connect()
        self._train_params()
        self.run_dir = run_dir

    def _step(self, action):
        action = np.squeeze(action)
        self.t += 1
        self.state, self.reward, self.done, self.info = self.gym.step(action)
        return np.float32(self.state), np.float32(self.reward), self.done

    def step(self, action, mode):
        if mode == 'tensorflow':
            if self.random_initialization:
                state, reward, done = tf.compat.v1.py_func(self._step, inp=[action], Tout=[tf.float32, tf.float32, tf.bool], name='env_step_func')
            else:
                state, reward, done = tf.compat.v1.py_func(self._step, inp=[action],
                                                 Tout=[tf.float32, tf.float32, tf.bool],
                                                 name='env_step_func')
            
            state = tf.reshape(state, shape=(self.state_size,))
            done.set_shape(())
        else:
            if self.random_initialization:
                state, reward, done = self._step(action)
            else:
                state, reward, done = self._step(action)

        return state, reward, done, 0.

    def reset(self):
        self.t = 0
        self.state = self.gym.reset()
        return self.state

    def get_status(self):
        return self.done

    def get_state(self):
        return self.state

    def render(self):
        self.gym.render()

    def _connect(self):
        self.action_size = self.gym.action_space.shape[0]
        self.action_space = np.asarray([None] * self.action_size)
        self.state_size = self.gym.observation_space.shape[0]
        self.qpos_size = 5
        self.qvel_size = 6

    def _train_params(self):
        self.trained_model = None
        self.train_mode = True
        self.expert_data = 'expert_trajectories/generated_ant_probs.hdf5'
        self.n_train_iters = 100000
        self.n_episodes_test = 5
        self.test_interval = 100
        self.n_steps_test = 500
        self.vis_flag = False
        self.save_models = True
        self.config_dir = None
        self.continuous_actions = True

        # Main parameters to play with:
        self.train_discriminator = True
        self.er_agent_size = 1000
        self.prep_time = 1000
        self.collect_experience_interval = 15
        self.n_steps_train = 10
        self.discr_policy_itrvl = 100
        self.gamma = 0.99
        self.batch_size = 70
        self.weight_decay = 1e-7
        self.policy_al_w = 1e-2
        self.policy_tr_w = 1e-4
        self.policy_accum_steps = 7
        self.total_trans_err_allowed = 1000
        self.temp = 1.
        self.cost_sensitive_weight = 0.8
        self.noise_intensity = 6.
        self.do_keep_prob = 0.75

        # Hidden layers size
        self.fm_size = 200
        self.d_size = [200, 100]
        self.p_size = [100, 50]

        # Learning rates
        self.fm_lr = 1e-4
        self.d_lr = 1e-3
        self.p_lr = 1e-4



