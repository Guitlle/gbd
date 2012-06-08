""" Age integrating models"""

import pylab as pl
import pymc as mc


def age_standardize_approx(name, age_weights, mu_age, age_start, age_end, ages):
    """ Generate PyMC objects for approximating the integral of gamma from age_start[i] to age_end[i]

    Parameters
    ----------
    name : str
    age_weights : array, len == len(ages)
    mu_age : pymc.Node with values of PCGP
    age_start, age_end : array

    Results
    -------
    Returns dict of PyMC objects, including 'mu_interval'
    the approximate integral of gamma  data predicted stochastic
    """
    cum_sum_weights = pl.cumsum(age_weights)

    @mc.deterministic(name='cum_sum_mu_%s'%name)
    def weighted_sum_mu(mu_age=mu_age, age_weights=age_weights):
        return pl.cumsum(mu_age*age_weights)

    age_start = age_start.__array__().clip(ages[0], ages[-1]) - ages[0]  # FIXME: Pandas bug, makes clip require __array__()
    age_end = age_end.__array__().clip(ages[0], ages[-1]) - ages[0]
    pl.seterr('ignore')
    @mc.deterministic(name='mu_interval_%s'%name)
    def mu_interval(weighted_sum_mu=weighted_sum_mu, cum_sum_weights=cum_sum_weights,
                    mu_age=mu_age,
                    age_start=pl.array(age_start, dtype=int),
                    age_end=pl.array(age_end, dtype=int)):
        mu = (weighted_sum_mu[age_end] - weighted_sum_mu[age_start]) / (cum_sum_weights[age_end] - cum_sum_weights[age_start])
        
        # correct cases where age_start == age_end
        i = age_start == age_end
        if pl.any(i):
            mu[i] = mu_age[age_start[i]]

        return mu

    return dict(mu_interval=mu_interval)

def age_integrate_approx(name, age_weights, mu_age, age_start, age_end, ages):
    """ Generate PyMC objects for approximating the integral of gamma from age_start[i] to age_end[i]

    Parameters
    ----------
    name : str
    age_weights : list of strings, each str a semicolon-separated list of floats
    mu_age : pymc.Node with values of PCGP
    age_start, age_end : array

    Results
    -------
    Returns dict of PyMC objects, including 'mu_interval'
    the approximate integral of gamma  data predicted stochastic
    """
    # FIXME: should use final age weight
    age_weights = [pl.array([1.e-9+float(w_ia) for w_ia in w_i.split(';')][:-1]) for w_i in age_weights]
    wt_sum = pl.array([sum(w_i) for w_i in age_weights])

    age_start = age_start.__array__().clip(ages[0], ages[-1]) - ages[0]  # FIXME: Pandas bug, makes clip require __array__()
    age_end = age_end.__array__().clip(ages[0], ages[-1]) - ages[0]
    pl.seterr('ignore')
    @mc.deterministic(name='mu_interval_%s'%name)
    def mu_interval(age_weights=age_weights,
                    wt_sum=wt_sum,
                    mu_age=mu_age,
                    age_start=pl.array(age_start, dtype=int),
                    age_end=pl.array(age_end, dtype=int)):
        N = len(age_weights)
        mu = pl.zeros(N)

        for i in range(N):
            mu[i] = pl.dot(age_weights[i], mu_age[age_start[i]:age_end[i]]) / wt_sum[i]

        return mu

    return dict(mu_interval=mu_interval)


def midpoint_approx(name, mu_age, age_start, age_end, ages):
    """ Generate PyMC objects for approximating the integral of gamma from age_start[i] to age_end[i]

    Parameters
    ----------
    name : str
    mu_age : pymc.Node with values of PCGP
    age_start, age_end : array

    Results
    -------
    Returns dict of PyMC objects, including 'mu_interval'
    the approximate integral of gamma  data predicted stochastic
    """
    age_mid = (age_start + age_end) / 2.
    @mc.deterministic(name='mu_interval_%s'%name)
    def mu_interval(mu_age=mu_age,
                    age_mid=pl.array(age_mid, dtype=int)):
        return mu_age.take(pl.clip(age_mid, ages[0], ages[-1]) - ages[0])

    return dict(mu_interval=mu_interval)


def midpoint_covariate_approx(name, mu_age, age_start, age_end, ages, transform=lambda x: x):
    """ Generate PyMC objects for approximating the integral of gamma from age_start[i] to age_end[i]

    Parameters
    ----------
    name : str
    mu_age : pymc.Node with values of PCGP
    age_start, age_end : array
    transform : function, optional

    Results
    -------
    Returns dict of PyMC objects, including 'mu_interval'
    the approximate integral of gamma  data predicted stochastic
    """
    theta = mc.Normal('theta_%s'%name, 0., 10.**-2, value=0.)

    age_mid = (age_start + age_end) / 2.
    age_width = transform(age_end - age_start)
    @mc.deterministic(name='mu_interval_%s'%name)
    def mu_interval(mu_age=mu_age,
                    theta=theta,
                    age_mid=pl.array(age_mid, dtype=int),
                    age_width=pl.array(age_width, dtype=float)):
        
        return mu_age.take(pl.clip(age_mid, ages[0], ages[-1]) - ages[0]) + theta*age_width

    return dict(mu_interval=mu_interval, theta=theta)
