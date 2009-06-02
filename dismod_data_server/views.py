from django.shortcuts import render_to_response, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import *
from django.core.urlresolvers import reverse
from django.utils.translation import ugettext as _
from django import forms

import pymc.gp as gp
import numpy as np
import pylab as pl
import csv

import gbd.fields
import gbd.view_utils as view_utils
from gbd.unicode_csv_reader import unicode_csv_reader
import dismod3

from models import *

def max_min_str(num_list):
    """ Return a nicely formated string denoting the range of a list of
    numbers.
    """
    if len(num_list) == 0:
        return '-'
    
    a = min(num_list)
    b = max(num_list)
    if a == b:
        return '%d' % a
    else:
        return '%d-%d' % (a,b)

def clean(str):
    """ Return a 'clean' version of a string, suitable for using as a hash
    string or a class attribute.
    """
    
    return str.strip().lower().replace(',', '').replace(' ', '_')
                

PER_PAGE = 10

def paginated_models(request, models_filter):
    """
    return a list of paginated objects, chosen from the models_filter and
    the page param of the get request.
    """
    from django.core.paginator import Paginator, InvalidPage, EmptyPage

    paginator = Paginator(models_filter, per_page=PER_PAGE)
    
    # Make sure page request is an int. If not, deliver first page.
    try:
        page = int(request.GET.get('page', '1'))
    except ValueError:
        page = 1
        
    try:
        models = paginator.page(page)
    except (EmptyPage, InvalidPage):
        models = paginator.page(paginator.num_pages)

    return models

class NewDataForm(forms.Form):
    required_data_fields = ['GBD Cause', 'Region', 'Parameter', 'Sex', 'Country',
                            'Age Start', 'Age End', 'Year Start', 'Year End',
                            'Parameter Value', 'Standard Error', 'Units', ]

    tab_separated_values = \
        forms.CharField(required=True,
                        widget=forms.Textarea(attrs={'rows':20, 'cols':80, 'wrap': 'off'}),
                        help_text=_('See <a href="/public/file_formats.html">file format specification</a> for details.'))

    def clean_tab_separated_values(self):
        tab_separated_values = self.cleaned_data['tab_separated_values']
        from StringIO import StringIO
        lines = unicode_csv_reader(StringIO(tab_separated_values), dialect='excel-tab')

        col_names = [clean(col) for col in lines.next()]

        # check that required fields appear
        for field in NewDataForm.required_data_fields:
            if not clean(field) in col_names:
                raise forms.ValidationError(_('Column "%s" is missing') % field)

        data_list = []
        for ii, cells in enumerate(lines):
            # skip blank lines
            if sum([cell == '' for cell in cells]) == len(cells):
                continue
            
            # ensure that something appears for each column
            if len(cells) != len(col_names):
                raise forms.ValidationError(
                    _('Error loading row %d:  found %d fields (expected %d))')
                    % (ii+2, len(cells), len(col_names)))

            # make an associative array from the row data
            data = {}
            for key, val in zip(col_names, cells):
                data[clean(key)] = val.strip()
                data['_row'] = ii+2

            data_list.append(data)

        # ensure that certain cells are the right format
        error_str = _('Row %d:  could not understand entry for %s')
        for r in data_list:
            try:
                r['parameter'] = gbd.fields.standardize_data_type[r['parameter']]
            except KeyError:
                raise forms.ValidationError(error_str % (r['_row'], 'Parameter'))
            try:
                r['sex'] = gbd.fields.standardize_sex[r['sex']]
            except KeyError:
                raise forms.ValidationError(error_str % (r['_row'], 'Sex'))
            try:
                r['age_start'] = int(r['age_start'])
                # some people think it is a good idea to use 99 as a missing value
                if r['age_start'] == 99:
                    r['age_start'] = 0
                    
                r['age_end'] = int(r['age_end'] or dismod3.MISSING)
                r['year_start'] = int(r['year_start'])
                r['year_end'] = int(r['year_end'])
            except (ValueError, KeyError):
                raise forms.ValidationError(
                    error_str % (r['_row'],
                                 'at least one of Age Start, Age End, Year Start, Year End'))
            try:
                r['parameter_value'] = float(r['parameter_value'])
            except ValueError:
                r['parameter_value'] = dismod3.MISSING

            try:
                r['standard_error'] = float(r['standard_error'])
            except ValueError:
                r['standard_error'] = dismod3.MISSING
                # raise forms.ValidationError(error_str % (r['_row'], 'Standard Error'))
            except KeyError:
                raise forms.ValidationError(error_str % (r['_row'], 'Standard Error'))
        return data_list


@login_required
def data_upload(request, id=-1):
    # if id != -1, append the data to DiseaseModel.get(id=id)
    if id == -1:
        dm = None
    else:
        dm = get_object_or_404(DiseaseModel, id=id)
        
    if request.method == 'GET':  # no form data is associated with page, yet
        form = NewDataForm()
    elif request.method == 'POST':  # If the form has been submitted...
        form = NewDataForm(request.POST)  # A form bound to the POST data

        if form.is_valid():
            # All validation rules pass, so create new data based on the
            # form contents
            data_table = form.cleaned_data['tab_separated_values']

            # make rates from rate_list
            data_list = []
            for d in data_table:
                # add a data point, save it on the data list
                args = {}
                args['condition'] = d['gbd_cause']
                args['gbd_region'] = d['region']
                args['region'] = d['country']
                args['data_type'] = d['parameter']
                args['sex'] = d['sex']
                args['age_start'] = d['age_start']
                args['age_end'] = d['age_end']
                args['year_start'] = d['year_start']
                args['year_end'] = d['year_end']

                args['value'] = d['parameter_value']
                args['standard_error'] = d['standard_error']

                # copy mapped data back into d, so that it appears in
                # params
                d.update(args)
                args['defaults'] = {'params_json': json.dumps(d)}

                d, is_new = Data.objects.get_or_create(**args)
                d.calculate_age_weights()
                data_list.append(d)
                
            # collect this data together into a new model
            args = {}
            args['condition'] = clean(', '.join(set([d.condition for d in data_list])))
            args['sex'] = 'all' #', '.join(set([d.sex for d in data_list]))
            args['region'] = 'global' #'; '.join(set([d.region for d in data_list]))
            args['year'] = '1990-2005' #max_min_str([d.year_start for d in data_list] + [d.year_end for d in data_list])
            if dm:
                dm = create_disease_model(dm.to_json())
            else:
                dm = DiseaseModel.objects.create(**args)
            for d in data_list:
                dm.data.add(d)
            dm.cache_params()
            dm.save()
            
            return HttpResponseRedirect(dm.get_absolute_url()) # Redirect after POST

    return render_to_response('data_upload.html', {'form': form, 'dm': dm})


@login_required
def data_show(request, id):
    data = get_object_or_404(Data, pk=id)
    data.view_list = [[_('Condition'), data.condition],
                      [_('Data Type'), data.data_type],
                      [_('Sex'), data.get_sex_display()],
                      [_('GBD Region'), data.gbd_region],
                      [_('Region'), data.region],
                      [_('Age'), data.age_str()],
                      [_('Year'), data.year_str()],
                      [_('Value'), data.value_str()],
                      ]
    return render_to_response('data_show.html', view_utils.template_params(data))

@login_required
def dismod_list(request, format='html'):
    dm_filter = DiseaseModel.objects.all().order_by('-id')
    if format == 'html':
        return render_to_response('dismod_list.html',
                                  {'paginated_models': paginated_models(request, dm_filter)})
    else:
        raise Http404

@login_required
def dismod_show(request, id, format='html'):
    if isinstance(id, DiseaseModel):
        dm = id
    else:
        dm = get_object_or_404(DiseaseModel, id=id)

    if format == 'html':
        dm.px_hash = dismod3.sparkplot_boxes(dm.to_json())
        return render_to_response('dismod_show.html', view_utils.template_params(dm))
    elif format == 'json':
        return HttpResponse(dm.to_json(), view_utils.MIMETYPE[format])
    elif format in ['png', 'svg', 'eps', 'pdf']:
        dismod3.tile_plot_disease_model(dm.to_json(),
                                        dismod3.utils.gbd_keys(type_list=dismod3.utils.output_data_types))
        return HttpResponse(view_utils.figure_data(format),
                            view_utils.MIMETYPE[format])
    else:
        raise Http404

@login_required
def dismod_find_and_show(request, condition, format='html'):
    try:
        dm = DiseaseModel.objects.filter(condition=condition).latest('id')
    except DiseaseModel.DoesNotExist:
        raise Http404
    return dismod_show(request, dm, format)

@login_required
def dismod_sparkplot(request, id, format='png'):
    dm = get_object_or_404(DiseaseModel, id=id)
    if format in ['png', 'svg', 'eps', 'pdf']:
        dismod3.sparkplot_disease_model(dm.to_json())
        return HttpResponse(view_utils.figure_data(format),
                            view_utils.MIMETYPE[format])
    else:
        raise Http404

@login_required
def dismod_overlay_plot(request, id, condition, type, region, year, sex, format='png'):
    if not format in ['png', 'svg', 'eps', 'pdf']:
        raise Http404

    dm = get_object_or_404(DiseaseModel, id=id)

    keys = dismod3.utils.gbd_keys(region_list=[region], year_list=[year], sex_list=[sex])
    dismod3.overlay_plot_disease_model(dm.to_json(), keys)
    pl.title('%s; %s; %s; %s' % (dismod3.plotting.prettify(condition),
                                 dismod3.plotting.prettify(region), year, sex))
    return HttpResponse(view_utils.figure_data(format),
                        view_utils.MIMETYPE[format])


@login_required
def dismod_tile_plot(request, id, condition, type, region, year, sex, format='png'):
    if not format in ['png', 'svg', 'eps', 'pdf']:
        raise Http404

    dm = get_object_or_404(DiseaseModel, id=id)

    keys = dismod3.utils.gbd_keys(region_list=[region], year_list=[year], sex_list=[sex])
    dismod3.tile_plot_disease_model(dm.to_json(), keys)
    return HttpResponse(view_utils.figure_data(format),
                        view_utils.MIMETYPE[format])


class NewDiseaseModelForm(forms.Form):
    model_json = \
        forms.CharField(required=True,
                        widget=forms.Textarea(attrs={'rows':20, 'cols':80, 'wrap': 'off'}),
                        help_text=_('See <a href="/public/dismod_data_json.html">dismod json specification</a> for details.'))
    def clean_model_json(self):
        model_json = self.cleaned_data['model_json']
        try:
            model_dict = json.loads(model_json)
        except ValueError:
            raise forms.ValidationError('JSON object could not be decoded')
        if not model_dict.get('params'):
            raise forms.ValidationError('missing params')
        for key in ['condition', 'sex', 'region', 'year']:
            if not model_dict['params'].get(key):
                raise forms.ValidationError('missing params.%s' % key)

        # store the model dict for future use
        self.cleaned_data['model_dict'] = model_dict
        return model_json

@login_required
def dismod_upload(request):
    if request.method == 'GET':  # no form data is associated with page, yet
        form = NewDiseaseModelForm()
    elif request.method == 'POST':  # If the form has been submitted...
        form = NewDiseaseModelForm(request.POST)  # A form bound to the POST data

        if form.is_valid():
            # All validation rules pass, so update or create new disease model
            model_dict = form.cleaned_data['model_dict']
            id = model_dict['params'].get('id', -1)
            if id > 0:
                dm = get_object_or_404(DiseaseModel, id=id)
                for key,val in model_dict['params'].items():
                    if type(val) == dict and dm.params.has_key(key):
                        dm.params[key].update(val)
                    else:
                        dm.params[key] = val
                dm.cache_params()
                dm.save()
            else:
                dm = create_disease_model(form.cleaned_data['model_json'])

            return HttpResponseRedirect(dm.get_absolute_url()) # Redirect after POST

    return render_to_response('dismod_upload.html', {'form': form})

@login_required
def job_queue_list(request):
    # accept format specified in url
    format = request.GET.get('format', 'html')

    dm_list = DiseaseModel.objects.filter(needs_to_run=True)
    if format == 'json':
        return HttpResponse(json.dumps([ dm.id for dm in dm_list ]),
                            view_utils.MIMETYPE[format])
    else:
        # more formats shall be added one day
        raise Http404
        
class JobRemovalForm(forms.Form):
    id = forms.IntegerField()
    
@login_required
def job_queue_remove(request):
    if request.method == 'GET':  # no form data is associated with page, yet
        form = JobRemovalForm()
    elif request.method == 'POST':  # If the form has been submitted...
        form = JobRemovalForm(request.POST)  # A form bound to the POST data

        if form.is_valid():
            dm = get_object_or_404(DiseaseModel, id=form.cleaned_data['id'])
            if dm.needs_to_run:
                dm.needs_to_run = False
                dm.save()

            return HttpResponseRedirect(
                reverse('gbd.dismod_data_server.views.job_queue_list') + '?format=json')
    return render_to_response('job_queue_remove.html', {'form': form})

@login_required
def job_queue_add(request, id):
    # only react to POST requests
    if request.method != 'POST':
        raise Http404

    dm = get_object_or_404(DiseaseModel, id=id)
    dm.needs_to_run = True
    if request.POST.has_key('estimate_type'):
        dm.params['estimate_type'] = request.POST['estimate_type']
    dm.cache_params()
    dm.save()

    return HttpResponseRedirect(dm.get_absolute_url())

class DisModAdjustForm(forms.Form):
    ymax = forms.FloatField(required=False, help_text=_('Maximum value of y-axis in summary plots.'))

    SMOOTHING_CHOICES = (
        ('', ''),
        ('(none)', 'No Prior'),
        ('1.0', 'Slightly'),
        ('10.0', 'Moderately'),
        ('100.0', 'Very'),
        )
    
    CONFIDENCE_CHOICES = (
        ('', ''),
        ('(none)', 'No Prior'),
        ('100.0 .0001', 'Not Confident'),
        ('1000.0 .0001', 'Moderately Confident'),
        ('5000.0 .0001', 'Very Confident'),
        )
    
    prevalence_smoothness = forms.ChoiceField(choices=SMOOTHING_CHOICES, required=False)
    prevalence_confidence = forms.ChoiceField(choices=CONFIDENCE_CHOICES, required=False)
    prevalence_zero_before = forms.RegexField(required=False, regex='(\d+)', error_messages={'invalid': 'Please enter a number'})
    prevalence_zero_after = forms.RegexField(required=False, regex='(\d+)', error_messages={'invalid': 'Please enter a number'}, help_text='p')

    incidence_smoothness = forms.ChoiceField(choices=SMOOTHING_CHOICES, required=False)
    incidence_confidence = forms.ChoiceField(choices=CONFIDENCE_CHOICES, required=False)
    incidence_zero_before = forms.RegexField(required=False, regex='(\d+)', error_messages={'invalid': 'Please enter a number'})
    incidence_zero_after = forms.RegexField(required=False, regex='(\d+)', error_messages={'invalid': 'Please enter a number'}, help_text='i')

    remission_smoothness = forms.ChoiceField(choices=SMOOTHING_CHOICES, required=False)
    remission_confidence = forms.ChoiceField(choices=CONFIDENCE_CHOICES, required=False)
    remission_zero_before = forms.RegexField(required=False, regex='(\d+)', error_messages={'invalid': 'Please enter a number'})
    remission_zero_after = forms.RegexField(required=False, regex='(\d+)', error_messages={'invalid': 'Please enter a number'}, help_text='r')

    case_fatality_smoothness = forms.ChoiceField(choices=SMOOTHING_CHOICES, required=False)
    case_fatality_confidence = forms.ChoiceField(choices=CONFIDENCE_CHOICES, required=False)
    case_fatality_zero_before = forms.RegexField(required=False, regex='(\d+)', error_messages={'invalid': 'Please enter a number'})
    case_fatality_zero_after = forms.RegexField(required=False, regex='(\d+)', error_messages={'invalid': 'Please enter a number'}, help_text='cf')


@login_required
def dismod_adjust(request, id):
    dm = get_object_or_404(DiseaseModel, id=id)
    
    if request.method == 'GET':  # no form data is associated with page, yet
        form = DisModAdjustForm()
    elif request.method == 'POST':  # If the form has been submitted...
        form = DisModAdjustForm(request.POST)  # A form bound to the POST data

        if form.is_valid():
            # do nothing if form is blank
            if np.any([bool(v) for v in form.cleaned_data.values()]):
                # if only ymax is set, don't create a new model
                ymax = form.cleaned_data.pop('ymax')
                if not np.any([bool(v) for v in form.cleaned_data.values()]):
                    dm.params['ymax'] = ymax
                    dm.cache_params()
                    dm.save()

                    return HttpResponseRedirect(dm.get_absolute_url())
            
                # otherwise, clone dm with new priors, and start running it
                else:
                    from gbd.dismod3.disease_json import DiseaseJson
                    dj = DiseaseJson(dm.to_json())
                    for k in dismod3.utils.gbd_keys(type_list=['%s']):
                        for type in ['incidence', 'prevalence', 'case_fatality', 'remission']:
                            prior_keys = [ s % type for s in ['%s_smoothness', '%s_confidence', '%s_zero_before', '%s_zero_after']]
                            prior_str = my_prior_str(form.cleaned_data, *prior_keys)
                            dj.set_priors(k % type, prior_str)

                    if ymax:
                        dj.set_ymax(ymax)
                        
                    new_dm = create_disease_model(dj.to_json())
                    return HttpResponseRedirect(new_dm.get_absolute_url())
    return render_to_response('dismod_adjust.html', {'form': form, 'dm': dm})
    

def my_prior_str(dict, smooth_key, conf_key, zero_before_key, zero_after_key):
    s = ''
    if dict.get(smooth_key) and dict[smooth_key] != '(none)':
        s += 'smooth %s, ' % dict[smooth_key]
    if dict.get(conf_key) and dict[conf_key] != '(none)':
        s += 'confidence %s, ' % dict[conf_key]
    if dict.get(zero_before_key):
        s += 'zero 0 %s, ' % dict[zero_before_key]
    if dict.get(zero_after_key):
        s += 'zero %s %d, ' % (dict[zero_after_key], dismod3.utils.MAX_AGE)

    return s
