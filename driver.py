import sys
import time
import numpy as np
import tensorflow as tf
import common
from mgail import MGAIL


class Driver(object):
    def __init__(self, environment, use_irl=False):
        self.use_irl = use_irl
        self.env = environment
        self.algorithm = MGAIL(environment=self.env, use_irl=use_irl)
        self.init_graph = tf.compat.v1.global_variables_initializer()
        self.saver = tf.compat.v1.train.Saver()
        self.sess = tf.compat.v1.Session()
        if self.env.trained_model:
            self.saver.restore(self.sess, self.env.trained_model)
        else:
            self.sess.run(self.init_graph)
        self.run_dir = self.env.run_dir
        self.loss = 999. * np.ones(3)
        self.policy_losses = []
        self.forward_losses = []
        self.disc_losses = []
        self.disc_acc = []
        self.reward_mean = 0
        self.reward_std = 0
        self.run_avg = 0.001
        self.discriminator_policy_switch = 0
        self.policy_loop_time = 0
        self.disc_acc = 0
        self.er_count = 0
        self.itr = 0
        self.best_reward = 0
        self.mode = 'Prep'
        np.set_printoptions(precision=2)
        np.set_printoptions(linewidth=220)

    def update_stats(self, module, attr, value):
        v = {'forward_model': 0, 'discriminator': 1, 'policy': 2}
        module_ind = v[module]
        if attr == 'loss':
            avg_loss = self.run_avg * self.loss[module_ind] + (1 - self.run_avg) * np.asarray(value)
            self.loss[module_ind] = avg_loss
            if module == 'policy':
                self.policy_losses.append(avg_loss)
            if module == 'discriminator':
                self.disc_losses.append(avg_loss)
            if module == 'forward_model':
                self.forward_losses.append(avg_loss)

        elif attr == 'accuracy':
            self.disc_acc = self.run_avg * self.disc_acc + (1 - self.run_avg) * np.asarray(value)
            # if module == 'discriminator':
            #     self.disc_losses.append(avg_loss)

    def train_forward_model(self):
        alg = self.algorithm
        states_, actions, _, states = self.algorithm.er_agent.sample()[:4]
        fetches = [alg.forward_model.minimize, alg.forward_model.loss]
        feed_dict = {alg.states_: states_, alg.states: states, alg.actions: actions,
                     alg.do_keep_prob: self.env.do_keep_prob}
        run_vals = self.sess.run(fetches, feed_dict)
        self.update_stats('forward_model', 'loss', run_vals[1])

    def train_discriminator(self):
        alg = self.algorithm
        # get states and actions
        if self.use_irl:
            state_a_, action_a, _, n_state_a, _, action_a_probs = self.algorithm.er_agent.sample()
            state_e_, action_e, _, n_state_e, _, action_e_probs = self.algorithm.er_expert.sample()
        else:
            state_a_, action_a, _, n_state_a, = self.algorithm.er_agent.sample()[:4]
            state_e_, action_e, _, n_state_e, = self.algorithm.er_expert.sample()[:4]

        states = np.concatenate([state_a_, state_e_])
        actions = np.concatenate([action_a, action_e])
        nstates = np.concatenate([n_state_a, n_state_e])
        # labels (policy/expert) : 0/1, and in 1-hot form: policy-[1,0], expert-[0,1]
        labels_a = np.zeros(shape=(state_a_.shape[0],))
        labels_e = np.ones(shape=(state_e_.shape[0],))
        labels = np.expand_dims(np.concatenate([labels_a, labels_e]), axis=1)

        fetches = [alg.discriminator.minimize, alg.discriminator.loss, alg.discriminator.acc]
        
        if self.use_irl:
            lprobs_a = action_a_probs # placeholder -> modify this to extract er's action_probs
            lprobs_e = action_e_probs # placeholder -> modify this to extract er's action_probs
            lprobs = np.concatenate([lprobs_a, lprobs_e], axis=0).astype(np.float32)
            
            feed_dict = {alg.states_: states, alg.actions: actions, alg.states: nstates,
                        alg.label: labels, alg.do_keep_prob: self.env.do_keep_prob,
                        alg.lprobs: lprobs, alg.gamma: self.env.gamma}
        else:
            feed_dict = {alg.states: states, alg.actions: actions,
                        alg.label: labels, alg.do_keep_prob: self.env.do_keep_prob}

        run_vals = self.sess.run(fetches, feed_dict)
        self.update_stats('discriminator', 'loss', run_vals[1])
        self.update_stats('discriminator', 'accuracy', run_vals[2])

    def train_policy(self):
        alg = self.algorithm

        # reset the policy gradient
        self.sess.run([alg.policy.reset_grad_op], {})

        # Adversarial Learning
        if self.env.get_status():
            state = self.env.reset()
        else:
            state = self.env.get_state()

        # Accumulate the (noisy) adversarial gradient
        for i in range(self.env.policy_accum_steps):
            # accumulate AL gradient
            fetches = [alg.policy.accum_grads_al, alg.policy.loss_al]
            feed_dict = {alg.states: np.array([state]), alg.gamma: self.env.gamma,
                         alg.do_keep_prob: self.env.do_keep_prob, alg.noise: 1., alg.temp: self.env.temp}
            run_vals = self.sess.run(fetches, feed_dict)
            self.update_stats('policy', 'loss', run_vals[1])

        # apply AL gradient
        self.sess.run([alg.policy.apply_grads_al], {})

    def collect_experience(self, record=1, vis=0, n_steps=None, noise_flag=True, start_at_zero=True):
        alg = self.algorithm

        # environment initialization point
        if start_at_zero:
            observation = self.env.reset()

        else:
            states, actions, rewards, posstates, terminals, action_a_probs = alg.er_expert.sample()
            observation = states[0]
        
        do_keep_prob = self.env.do_keep_prob
        t = 0
        R = 0
        done = 0
        if n_steps is None:
            n_steps = self.env.n_steps_test

        while not done:
            if vis:
                self.env.render()

            if not noise_flag:
                do_keep_prob = 1.
            
            a, a_probs = self.sess.run(fetches=[alg.action_test, alg.action_probs_test], feed_dict={alg.states: np.reshape(observation, [1, -1]),
                                                                    alg.do_keep_prob: do_keep_prob,
                                                                    alg.noise: noise_flag,
                                                                    alg.temp: self.env.temp})
            # a_probs = common.compute_action_probs(a, a_means, self.env.sigma.reshape(1, -1))

            observation, reward, done, info = self.env.step(a, mode='python')
            done = done or t > n_steps
            t += 1
            R += reward

            if record:
                if self.env.continuous_actions:
                    action = a
                else:
                    action = np.zeros((1, self.env.action_size))
                    action[0, a[0]] = 1
                alg.er_agent.add(actions=action, action_probs=a_probs, rewards=[reward], next_states=[observation], terminals=[done])

        return R

    def train_step(self):
        # phase_1 - Adversarial training
        # forward_model: learning from agent data
        # discriminator: learning in an interleaved mode with policy
        # policy: learning in adversarial mode

        # Fill Experience Buffer
        if self.itr == 0:
            while self.algorithm.er_agent.current == self.algorithm.er_agent.count:
                self.collect_experience()
                buf = 'Collecting examples...%d/%d' % \
                      (self.algorithm.er_agent.current, self.algorithm.er_agent.states.shape[0])
                sys.stdout.write('\r' + buf)

        # Adversarial Learning
        else:
            self.train_forward_model()

            if self.env.train_discriminator:
                self.mode = 'Prep'
            else:
                self.mode = "AL"            
            if self.env.train_discriminator and self.itr < self.env.prep_time:
                self.train_discriminator()
            else:
                self.mode = 'AL'

                if self.env.train_discriminator and self.discriminator_policy_switch:
                    self.train_discriminator()
                else:
                    self.train_policy()

                if self.itr % self.env.collect_experience_interval == 0:
                    self.collect_experience(start_at_zero=False, n_steps=self.env.n_steps_train)

                # switch discriminator-policy
                if self.itr % self.env.discr_policy_itrvl == 0:
                    self.discriminator_policy_switch = not self.discriminator_policy_switch

        # print progress
        if self.itr % 100 == 0:
            self.print_info_line('slim')

    def print_info_line(self, mode):
        if mode == 'full':
            buf = '%s Training(%s): iter %d, loss: %s R: %.1f, R_std: %.2f\n' % \
                  (time.strftime("%H:%M:%S"), self.mode, self.itr, self.loss, self.reward_mean, self.reward_std)
        else:
            buf = "processing iter: %d, loss(forward_model,discriminator,policy): %s" % (self.itr, self.loss)
        sys.stdout.write('\r' + buf)

    def save_model(self, dir_name=None, best=False, prefix=None):
        import os
        if dir_name is None:
            dir_name = self.run_dir + '/snapshots/'
        if not os.path.isdir(dir_name):
            os.mkdir(dir_name)
        if not best:
            fname = dir_name + time.strftime("%Y-%m-%d-%H-%M-") + ('%0.6d.sn' % self.itr)
        else:
            fname = dir_name + 'best/' + prefix + '-best'

        common.save_params(fname=fname, saver=self.saver, session=self.sess)
