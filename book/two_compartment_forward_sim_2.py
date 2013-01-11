# -*- coding: utf-8 -*-
# <nbformat>3.0</nbformat>

# <codecell>

""" Generate consistent prevalence rates as function of age from
incidence, remission, and excess-mortality"""

# <codecell>

import sys
sys.path += ['..', '../..']

import pylab as pl
import pymc as mc
import pandas

import consistent_model
import data_simulation

import book_graphics
reload(book_graphics)

# <codecell>

### @export 'initialize-model'
types = pl.array(['i', 'r', 'f', 'p'])
model = data_simulation.simple_model(0)
model.input_data = pandas.read_csv('/home/j/Project/dismod/gbd/data/ssas_mx.csv')

ages = pl.array([0, 5, 15, 25, 35, 45, 55, 65, 75, 100])
for t in types:
    model.parameters[t]['parameter_age_mesh'] = ages

model.vars = consistent_model.consistent_model(model, 'all', 'total', 'all', {})
for i, k_i in enumerate(model.parameters[t]['parameter_age_mesh']):
    model.vars['i']['gamma'][i].value = pl.log(k_i*.0001 + .001)
    model.vars['r']['gamma'][i].value = pl.log(.1)
    model.vars['f']['gamma'][i].value = pl.log(.05)

# <codecell>

### @export 'initial-rates'

#book_graphics.plot_age_patterns(model, types='i r m f p'.split(),
#                                yticks=dict(i=[0,.01,.02], r=[0,.05,.1], m=[0,.2,.4], f=[0,.05,.1], p=[0,.05,.1]))

def set_rate(rate_type, value):
    t = {'incidence':'i', 'remission': 'r', 'excess-mortality': 'f'}[rate_type]
    for i, k_i in enumerate(model.vars[t]['knots']):
        model.vars[t]['gamma'][i].value = pl.log(pl.maximum(1.e-9, value[i]))

def set_birth_prev(value):
    model.vars['logit_C0'].value = mc.logit(pl.maximum(1.e-9, value))

# <codecell>

### @export 'mental'
set_rate('remission', pl.ones_like(ages)*.25)
set_rate('incidence', pl.where((ages > 14) & (ages < 65), (65-ages)*.001, 0.))
set_birth_prev(0)
set_rate('excess-mortality', 1e-4*pl.ones_like(ages))

book_graphics.plot_age_patterns(model, yticks=[0,.2,.4], panel='a')
pl.savefig('forward-sim-mental.pdf')

# <codecell>

### @export 'congenital'
set_rate('remission', pl.zeros_like(ages))
set_rate('incidence', pl.zeros_like(ages))
set_birth_prev(.2)
set_rate('excess-mortality', .5*(ages/100.)**2)

reload(book_graphics)
book_graphics.plot_age_patterns(model, yticks=[0,.2,.4], panel='b')
pl.savefig('forward-sim-congenital.pdf')

# <codecell>

### @export 'old_age'
set_rate('remission', pl.ones_like(ages)*0.)
set_rate('incidence', pl.where(ages > 50, pl.exp((ages-50.)/25.)*.01, 0.))
set_birth_prev(0)
set_rate('excess-mortality', pl.exp(ages/25.)*.01)

book_graphics.plot_age_patterns(model, yticks=[0,.2,.4], panel='c')
pl.savefig('forward-sim-old_age.pdf')

# <codecell>

### @export 'reproductive'
set_rate('remission', pl.where(ages<45, .1, .35))
set_rate('incidence', pl.where((ages>14) & (ages<65), .025, 0.))
set_birth_prev(0)
set_rate('excess-mortality', pl.zeros_like(ages))

book_graphics.plot_age_patterns(model, yticks=[0,.2,.4], panel='d')
pl.savefig('forward-sim-reproductive.pdf')

# <codecell>

### @export 'incidence_pulse'
set_rate('remission', 0*ages)
set_rate('incidence', pl.where(ages==15, .02, 0.))
set_birth_prev(0)
set_rate('excess-mortality', 0*ages)

book_graphics.plot_age_patterns(model, yticks=[0,.2,.4], panel='e')
pl.savefig('forward-sim-incidence_pulse.pdf')

# <codecell>


