""" Where midpoint model works and does not
"""

# add to path, to make importing possible
import sys
sys.path += ['.', '..']

import pylab as pl
import pymc as mc
import scipy.interpolate

import graphics
import book_graphics
reload(book_graphics)


import age_group_models as agm
reload(agm)

m = {}

mc.np.random.seed(12345)
f = scipy.interpolate.interp1d([0, 20, 40, 60, 100], [0, .1, .9, .2, 0])
model = agm.simulate_age_group_data(N=25, delta_true=5e2, pi_true=f)
agm.fit_age_standardizing_model(model)

m[0] = model

mc.np.random.seed(12345)
f = scipy.interpolate.interp1d([0, 20, 40, 60, 100], [0, .1, .9, .2, 0])
model = agm.simulate_age_group_data(N=25, delta_true=5, pi_true=f)
agm.fit_age_standardizing_model(model)
m[1] = model

agm.plot_fits(m)
pl.savefig('book/graphics/age_group_standardize.pdf')

pl.show()
