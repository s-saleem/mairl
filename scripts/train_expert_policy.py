#!/usr/bin/env python3
import gym
from gym_minigrid.wrappers import *
from garage import wrap_experiment
from garage.envs import GarageEnv
from garage.experiment import LocalTFRunner
from garage.experiment.deterministic import set_seed
from garage.np.baselines import LinearFeatureBaseline
from garage.tf.baselines import GaussianCNNBaseline, GaussianMLPBaseline
from garage.tf.algos import TRPO
from garage.tf.policies import CategoricalMLPPolicy, GaussianMLPPolicy
import pybulletgym

from akro.discrete import Discrete

@wrap_experiment
def trpo_minigrid(ctxt=None, seed=1):
    """Train TRPO with MiniGrid-FourRooms-v0 environment.
    Args:
        ctxt (garage.experiment.ExperimentContext): The experiment
            configuration used by LocalRunner to create the snapshotter.
        seed (int): Used to seed the random number generator to produce
            determinism.
    """
    set_seed(seed)
    with LocalTFRunner(ctxt) as runner:

        env = GarageEnv(env_name='DisabledAntPyBulletEnv-v0')

        policy = GaussianMLPPolicy(name='policy',

                                      env_spec=env.spec,
                                      hidden_sizes=(128, 64, 32))

        # baseline = LinearFeatureBaseline(env_spec=env.spec)
        baseline = GaussianMLPBaseline(
            env_spec=env.spec
        )

        algo = TRPO(env_spec=env.spec,
                    policy=policy,
                    baseline=baseline,
                    discount=0.99,

                    max_kl_step=0.001)

        runner.setup(algo, env)
        runner.train(n_epochs=2000, batch_size=4000)



trpo_minigrid()
