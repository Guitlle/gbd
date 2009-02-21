from django.shortcuts import render_to_response, get_object_or_404
from django.http import *
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext as _

import pymc.gp as gp
import numpy as np
import pylab as pl

from dismod3.models import Rate
import view_utils

def rate_show(request, id):
    rate = get_object_or_404(Rate, pk=id)
    rate.view_list = [[_('Disease'), rate.disease],
                      [_('Rate Type'), rate.get_rate_type_display()],
                      [_('Sex'), rate.get_sex_display()],
                      [_('Region'), rate.region],
                      [_('Country'), rate.country],
                      [_('Age Range'), '%d-%d' % (rate.age_start, rate.age_end)],
                      [_('Epoch'), '%d-%d' % (rate.epoch_start, rate.epoch_end)],
                      [_('Rate'), '%d/%d = %0.5f' % (rate.numerator, rate.denominator, rate.rate)],
                      ]
    return render_to_response('rate/show.html', view_utils.template_params(rate))

def rate_redirect(request, id, action):
    rate = get_object_or_404(Rate, pk=id)
    if action == 'edit':
        url = '/admin/dismod3/rate/%d' % rate.id
    elif action in view_utils.command_list['move']:
        url = reverse('dismod3.views.rate_show', args=(rate.id+view_utils.id_delta[action],))
    elif action in view_utils.command_list['sex']:
        url = '/rate/plot/disease_%s-rate_%s-region_%s-sex_%s.png' % (rate.disease.id, rate.rate_type[:4], rate.region.id, action)
    elif action in view_utils.command_list['format']:
        url = '/rate/plot/disease_%s-rate_%s-region_%s-sex_%s.%s' % (rate.disease.id, rate.rate_type[:4], rate.region.id, rate.sex, action)
    else:
        raise Http404
    
    return HttpResponseRedirect(url)

def rate_plot(request, path, format='png'):
    """
    use matplotlib plotting functions to render transparent
    rectangles on the current figure representing each
    piece of RateData that will be used in fitting this
    age-specific rate function

    path is the format param-value+param2-value2+..., where
    each param is from the list
      [disease, rate, region, sex, limit]
    values for region and disease are the id of the object,
    limit is an int upper-bound on number of rates to plot,
    and all the other options will do partial name matching
    """
    filter_params = {'limit': '100'}
    for p in path.split('-'):
        param, value = p.split('_')
        if param == 'disease':
            filter_params['disease__id'] = int(value)
        elif param == 'rate':
            filter_params['rate_type__contains'] = value
        elif param == 'region':
            filter_params['region__id'] = int(value)
        elif param == 'sex':
            filter_params['sex'] = value
        elif param == 'limit':
            filter_params['limit'] = value
            
    limit = int(filter_params.pop('limit'))
    rates = Rate.objects.filter(**filter_params)

    view_utils.clear_plot()
    for r in rates[:limit]:
        rate_val = float(r.numerator)/float(r.denominator)
        x_jitter = np.random.rand()
        y_jitter = 0.
        if r.sex == 'male':
            color = (0.,0.,.8)
        elif r.sex == 'female':
            color = (.8,0.,0.)
        else:
            color = (0.,.8,0.)
            
        text_color = 'black'
        alpha=.65
        pl.plot(np.array([r.age_start, r.age_end+1.])+x_jitter, 
                np.array([rate_val,rate_val])+y_jitter,
                color=color, alpha=alpha, linewidth=5,)
        pl.text(r.age_end+x_jitter, rate_val+y_jitter,
                "n=%d" % r.denominator,
                color=text_color, alpha=alpha, fontsize=6)
    view_utils.label_plot(path.replace('-', ', ').replace('_', ': '))

    
    return HttpResponse(view_utils.figure_data(format),
                        view_utils.MIMETYPE[format])
