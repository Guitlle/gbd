from django.test import TestCase
from django.test.client import Client

from django.core.urlresolvers import reverse
import urllib

from models import *

class DisModDataServerTestCase(TestCase):
    fixtures = ['dismod_data_server/fixtures',
                'population_data_server/fixtures']

    def create_users(self):
        """ Create users for functional testing of access control.

        It seems easier to create the users with a code block than as
        json fixtures, because the password is clearer before it is
        encrypted.
        """
        from django.contrib.auth.models import User
        user = User.objects.create_user('red', '', 'red')
        user = User.objects.create_user('green', '', 'green')
        user = User.objects.create_user('blue', '', 'blue')

    def assertPng(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content[1:4], 'PNG')

    def assertSuccess(self, response):
        return self.assertEquals(response.status_code, 200)

    def setUp(self):
        self.dm = DiseaseModel.objects.latest('id')
        self.data = Data.objects.latest('id')

        self.create_users()

    # unit tests
    def test_str(self):
        """ Test all model string functions"""
        s = str(self.data)
        self.assertTrue(isinstance(s,str))

        s = self.data.get_absolute_url()
        self.assertTrue(isinstance(s,str))

        s = str(self.dm)
        self.assertTrue(isinstance(s,str))

        s = self.dm.get_absolute_url()
        self.assertTrue(isinstance(s,str))

    def test_calculate_and_cache_age_weights(self):
        """ Test that dismod data object can query to population data server"""
        self.assertFalse(self.data.params.has_key('age_weights'))

        age_weights = self.data.age_weights()
        self.assertTrue(self.data.params.has_key('age_weights'))

        # fixture has population skewed towards youth
        self.assertTrue(age_weights[0] > age_weights[1])

    def test_create_disease_model(self):
        """ Test creating a dismod model object from a dismod_data json string"""

        json_str = self.dm.to_json()
        dm2 = create_disease_model(json_str)
        self.assertTrue(dm2.id != self.dm.id and
                        dm2.id == DiseaseModel.objects.latest('id').id)
        
    # functional tests
    #### Data Loading requirements

    def test_dismod_load_data_from_file(self):
        """ Make sure that a properly formatted data csv file can be loaded over the web"""

        c = Client()

        # first check that create requires a login
        url = reverse('gbd.dismod_data_server.views.data_upload')
        response = c.get(url)
        self.assertRedirects(response, '/accounts/login/?next=%s'%url)

        # then login and do functional tests
        c.login(username='red', password='red')

        response = c.get(url)
        self.assertTemplateUsed(response, 'data_upload.html')

        response = c.post(url, {})
        self.assertTemplateUsed(response, 'data_upload.html')

        # now do it right, and make sure that data and datasets are added
        f = open("tests/diabetes_data.tsv")
        response = c.post(url, {'file':f})
        f.close()
        self.assertRedirects(response, reverse('gbd.dismod_data_server.views.dismod_summary', args=[DiseaseModel.objects.latest('id').id]))

    def test_dismod_load_well_formed_data_csv(self):
        """ Make sure that a properly formatted data csv can be loaded over the web"""

        # TODO: fix this test, which was broken when asynchronous
        # age_weight calculation was added to views.py
        
        c = Client()

        # first check that create requires a login
        url = reverse('gbd.dismod_data_server.views.data_upload')
        response = c.get(url)
        self.assertRedirects(response, '/accounts/login/?next=%s'%url)

        # then login and do functional tests
        c.login(username='red', password='red')

        response = c.get(url)
        self.assertTemplateUsed(response, 'data_upload.html')
        
        response = c.post(url, {'tab_separated_values': '', 'file': ''})
        self.assertTemplateUsed(response, 'data_upload.html')

        # now do it right, and make sure that data and datasets are added
        response = c.post(url, {'tab_separated_values': \
        'GBD Cause\tRegion\tParameter\tSex\tCountry\tAge Start\tAge End\tYear Start\tYear End\tParameter Value\tStandard Error\tUnits\tType of Bound\nCannabis Dependence\tWorld\tPrevalence\tTotal\tCanada\t15\t24\t2005\t2005\t.5\t.1\tper 1.0\t95% CI'})

        self.assertRedirects(response, reverse('gbd.dismod_data_server.views.dismod_summary', args=[DiseaseModel.objects.latest('id').id]))
        #self.assertEqual([1.]*10, Data.objects.latest('id').params.get('age_weights'))

    def test_dismod_informative_error_for_badly_formed_data_csv(self):
        """ Provide informative error if data csv cannot be loaded"""
        c = Client()
        url = reverse('gbd.dismod_data_server.views.data_upload')
        c.login(username='red', password='red')

        # csv with required column, GBD Cause,  missing 
        response = c.post(url, {'tab_separated_values': \
        'Region\tParameter\tSex\tCountry\tAge Start\tAge End\tYear Start\tYear End\tParameter Value\tStandard Error\tUnits\tType of Bound\nWorld\tPrevalence\tTotal\tAustralia\t15\t24\t2005\t2005\t.5\t.1\tper 1.0\t95% CI'})
        self.assertContains(response, 'GBD Cause')
        self.assertContains(response, 'is missing')

        # csv with cell missing from line 2
        response = c.post(url, {'tab_separated_values': \
        'GBD Cause\tRegion\tParameter\tSex\tCountry\tAge Start\tAge End\tYear Start\tYear End\tParameter Value\tStandard Error\tUnits\tType of Bound\nCannabis Dependence\tWorld\tPrevalence\tTotal\tAustralia\t15\t24\t2005\t2005\t.5\t.1\tper 1.0'})
        self.assertContains(response, 'Error loading row 2:')

        # csv with unrecognized parameter
        response = c.post(url, {'tab_separated_values': \
        'GBD Cause\tRegion\tParameter\tSex\tCountry\tAge Start\tAge End\tYear Start\tYear End\tParameter Value\tStandard Error\tUnits\tType of Bound\nCannabis Dependence\tWorld\tPrevalenceee\tTotal\tAustralia\t15\t24\t2005\t2005\t.5\t.1\tper 1.0\t95% CI'})
        self.assertContains(response, 'Row 2:  could not understand entry for Parameter')

    def test_dismod_add_age_weights_to_data(self):
        """ Use the Population Data Server to get the age weights for a new piece of data"""

        # TODO: fix this test, which was broken when asynchronous
        # age_weight calculation was added to views.py

        c = Client()
        url = reverse('gbd.dismod_data_server.views.data_upload')
        c.login(username='red', password='red')

        response = c.post(url, {'tab_separated_values': \
        'GBD Cause\tRegion\tParameter\tSex\tCountry\tAge Start\tAge End\tYear Start\tYear End\tParameter Value\tStandard Error\tUnits\tType of Bound\nCannabis Dependence\tWorld\tPrevalence\tTotal\tAustralia\t15\t24\t2005\t2005\t.5\t.1\tper 1.0\t95% CI'})

        id = DiseaseModel.objects.latest('id').id
        self.assertRedirects(response, reverse('gbd.dismod_data_server.views.dismod_summary', args=[id]))

        response = c.post(reverse('gbd.dismod_data_server.views.dismod_update_covariates', args=[id]))
        age_weights = Data.objects.latest('id').params.get('age_weights')
        # the fixture for Australia 2005 total population has a downward trend
        assert age_weights[0] > age_weights[1]
        self.assertRedirects(response, reverse('gbd.dismod_data_server.views.dismod_run', args=[DiseaseModel.objects.latest('id').id]))

    def test_dismod_add_covariates_to_data(self):
        """ Use the Covariate Data Server to get the covariates for a new piece of data"""
        c = Client()
        url = reverse('gbd.dismod_data_server.views.data_upload')
        c.login(username='red', password='red')

        response = c.post(url, {'tab_separated_values': \
        'GBD Cause\tRegion\tParameter\tSex\tCountry\tAge Start\tAge End\tYear Start\tYear End\tParameter Value\tStandard Error\tUnits\tType of Bound\nCannabis Dependence\tWorld\tPrevalence\tTotal\tAustralia\t15\t24\t2005\t2005\t.5\t.1\tper 1.0\t95% CI'})

        assert Data.objects.latest('id').params.has_key('gdp'), \
            'should add GDP data from covariate data server (not yet implemented)'
        
    def test_dismod_add_additional_data_to_model(self):
        """ Test adding data from csv to existing model"""
        c = Client()
        c.login(username='red', password='red')

        self.data.cache_params()
        self.data.save()
        
        self.dm.data.add(self.data)
        
        url = reverse('gbd.dismod_data_server.views.data_upload', args=(self.dm.id,))

        response = c.get(url)
        self.assertTemplateUsed(response, 'data_upload.html')

        response = c.post(url, {'tab_separated_values': \
        'GBD Cause\tRegion\tParameter\tSex\tCountry\tAge Start\tAge End\tYear Start\tYear End\tParameter Value\tStandard Error\tUnits\tType of Bound\nCannabis Dependence\tWorld\tPrevalence\tTotal\tCanada\t15\t24\t2015\t2015\t.5\t.1\tper 1.0\t95% CI'})

        newest_data = Data.objects.latest('id')
        newest_dm = DiseaseModel.objects.latest('id')
        self.assertRedirects(response, reverse('gbd.dismod_data_server.views.dismod_summary', args=[newest_dm.id]))
        self.assertEqual(sorted([d.id for d in self.dm.data.all()] + [newest_data.id]),
                         sorted([d.id for d in newest_dm.data.all()]))
        
        
    #### Model Viewing requirements
    def test_data_show(self):
        """ Test displaying html version of a single data point"""
        c = Client()

        # first check that show requires login
        url = self.data.get_absolute_url()
        response = c.get(url)
        self.assertRedirects(response, '/accounts/login/?next=%s'%url)

        # then check that show works after login
        c.login(username='red', password='red')
        response = c.get(url)
        self.assertTemplateUsed(response, 'data_show.html')

    def test_dismod_list(self):
        """ Test listing the existing disease models"""
        c = Client()

        # first check that show requires login
        url = reverse('gbd.dismod_data_server.views.dismod_list')
        response = c.get(url)
        self.assertRedirects(response, '/accounts/login/?next=%s'%url)

        # then login and do functional tests
        c.login(username='red', password='red')
        response = c.get(url)
        self.assertTemplateUsed(response, 'dismod_list.html')

    def test_dismod_show(self):
        """ Test displaying html version of a disease model"""
        c = Client()

        # first check that show requires login
        url = self.dm.get_absolute_url()
        response = c.get(url)
        self.assertRedirects(response, '/accounts/login/?next=%s'%url)

        # then check that show works after login
        c.login(username='red', password='red')
        response = c.get(url)
        self.assertTemplateUsed(response, 'dismod_show.html')

    def test_dismod_show_in_other_formats(self):
        """ Test displaying disease model as png, json, csv, etc"""
        c = Client()
        c.login(username='red', password='red')
        url = self.dm.get_absolute_url()

        # test png
        # (commented out, because it takes 30 seconds to run!)
        #response = c.get(url + '.png')
        #self.assertPng(response)

    def test_dismod_sparkplot(self):
        """ Test sparkplot of disease model"""
        c = Client()

        # first check that sparkplot requires login
        url = '/dismod/show/spark_%d.png' % self.dm.id
        response = c.get(url)
        self.assertRedirects(response, '/accounts/login/?next=%s'%url)

        # then check that it works after login
        c.login(username='red', password='red')
        response = c.get(url)
        self.assertPng(response)

    def test_dismod_overlay_plot(self):
        """ Test overlay plot of disease model"""
        c = Client()

        # first check that overlay plot requires login
        url = '/dismod/show/overlay_1_CHD+all+latin_america_southern+1995+male.png'
        response = c.get(url)
        self.assertRedirects(response, '/accounts/login/?next=%s' % urllib.quote(url))

        # then check that it works after login
        c.login(username='red', password='red')
        response = c.get(url)
        self.assertPng(response)

    def test_dismod_tile_plot(self):
        """ Test tile plot of disease model"""
        c = Client()

        # first check that overlay plot requires login
        url = '/dismod/show/tile_1_CHD+all+latin_america_southern+1995+male.png'
        response = c.get(url)
        self.assertRedirects(response, '/accounts/login/?next=%s' % urllib.quote(url))

        # then check that it works after login
        c.login(username='red', password='red')
        response = c.get(url)
        self.assertPng(response)

    def test_dismod_summary(self):
        """ Test the model summary view"""
        c = Client()

        # first check that overlay plot requires login
        url = reverse('gbd.dismod_data_server.views.dismod_summary', args=[self.dm.id])
        response = c.get(url)
        self.assertRedirects(response, '/accounts/login/?next=%s'%url)

        # then check that it works after login
        c.login(username='red', password='red')
        response = c.get(url)
        self.assertTemplateUsed(response, 'dismod_summary.html')
        
    
    #### Model Running requirements
    def test_get_model_json(self):
        """ Test getting a json encoding of the disease model"""
        c = Client()
        
        # first check that getting json requires login
        url = self.dm.get_absolute_url() + '.json'
        response = c.get(url)
        self.assertRedirects(response, '/accounts/login/?next=%s'%url)

        # now login, and check that you can get json
        c.login(username='red', password='red')
        response = c.get(url)
        r_json = json.loads(response.content)
        self.assertEqual(set(r_json.keys()), set(['params', 'data']))
        
    def test_post_model_json(self):
        """ Test posting a json encoding of the disease model"""
        c = Client()

        # first check that create requires a login
        url = reverse('gbd.dismod_data_server.views.dismod_upload')
        response = c.get(url)
        self.assertRedirects(response, '/accounts/login/?next=%s'%url)

        # then login and do functional tests
        c.login(username='red', password='red')
        response = c.get(url)
        self.assertTemplateUsed(response, 'dismod_upload.html')

        # check that bad input is rejected
        # TODO: make this part of the test more extensive
        response = c.post(url, {'model_json': ''})
        self.assertTemplateUsed(response, 'dismod_upload.html')

        # check that if input is good and params.id equals a valid
        # model id, that model is updated
        self.dm.params['map'] = {'prevalence': [0,0,0,0], 'incidence': [0,0,0,0]}
        response = c.post(url, {'model_json': self.dm.to_json()})
        self.assertRedirects(response, self.dm.get_absolute_url())
        dm = DiseaseModel.objects.get(id=self.dm.id)
        self.assertEqual(dm.params['map']['prevalence'], [0,0,0,0])
        

        # now check that good input is accepted, and if params.id = -1
        # a new model is created
        initial_dm_cnt = DiseaseModel.objects.count()
        self.dm.id = -1
        response = c.post(url, {'model_json': self.dm.to_json()})
        self.assertRedirects(response, DiseaseModel.objects.latest('id').get_absolute_url())
        self.assertEqual(DiseaseModel.objects.count(), initial_dm_cnt+1)
        

    def test_get_job_queue_list_and_remove(self):
        """ Test getting list of jobs waiting on queue to run"""
        c = Client()
        c.login(username='red', password='red')

        # make a model need to run
        self.dm.needs_to_run = True
        self.dm.save()

        # test GET list
        url = reverse('gbd.dismod_data_server.views.job_queue_list')
        response = c.get(url, {'format': 'json'})

        r_json = json.loads(response.content)
        self.assertEqual(r_json, [self.dm.id])

        # test GET&POST remove
        self.assertTrue(self.dm.needs_to_run)
        url = reverse('gbd.dismod_data_server.views.job_queue_remove')
        response = c.get(url)
        response = c.post(url, {'id': self.dm.id})

        dm = DiseaseModel.objects.get(id=self.dm.id)
        self.assertFalse(dm.needs_to_run)
        

    def test_job_queue_add(self):
        """ Test adding a job to job queue to run"""
        c = Client()
        c.login(username='red', password='red')

        self.assertFalse(self.dm.needs_to_run)
        url = reverse('gbd.dismod_data_server.views.job_queue_add', args=[self.dm.id])
        response = c.post(url, {'estimate_type': 'fit each region/year/sex individually'})
        dm = DiseaseModel.objects.get(id=self.dm.id)
        self.assertTrue(dm.needs_to_run)
        self.assertEqual(dm.params.get('estimate_type'), 'fit each region/year/sex individually')

    def test_dismod_run(self):
        """ Test adding a job to job queue to run"""
        c = Client()
        c.login(username='red', password='red')

        url = reverse('gbd.dismod_data_server.views.dismod_run', args=[self.dm.id])
        response = c.get(url)
        self.assertTemplateUsed(response, 'dismod_run.html')

    def test_dismod_update_covariates(self):
        """ Test updating age weights for a model"""
        c = Client()
        c.login(username='red', password='red')

        url = reverse('gbd.dismod_data_server.views.dismod_update_covariates', args=[self.dm.id])
        response = c.post(url)
        self.assertRedirects(response, reverse('gbd.dismod_data_server.views.dismod_run', args=[self.dm.id]))
        

    # Model Adjusting Requirements
# This is currently handled by a Java Applet, but the test is for the previous implementation,
# an html form.  Perhaps we will go back to an html form in the future.
#     def test_dismod_adjust(self):
#         """ Test changing priors and ymax for a model"""
#         c = Client()

#         # first check that this requires login
#         url = reverse('gbd.dismod_data_server.views.dismod_adjust', args=[self.dm.id])
#         response = c.get(url)
#         self.assertRedirects(response, '/accounts/login/?next=%s'%url)

#         # now login, and check that you can get to adjust page
#         c.login(username='red', password='red')
#         response = c.get(url)

#         # post with no adjustments, this should not change the model
#         response = c.post(url, {})
#         self.assertSuccess(response)
        
#         # now make ymax adjustments, and check that they actually change ymax
#         response = c.post(url, {'ymax' : '0.1'})
        
#         dm = DiseaseModel.objects.get(id=self.dm.id)
#         self.assertRedirects(response, dm.get_absolute_url())
#         self.assertEqual(dm.params['ymax'], .1)
        
#         # now make prior adjustments, and check
#         response = c.post(url, {'prevalence_smoothness' : '10.0'})
        
#         new_dm = DiseaseModel.objects.latest('id')
#         self.assertRedirects(response, reverse('gbd.dismod_data_server.views.dismod_run', args=[new_dm.id]))
#         self.assertEqual(new_dm.params['priors']['prevalence+north_america_high_income+2005+male'], 'smooth 10.0, ')
        
    def test_dismod_preview_priors(self):
        """ Test generating png to preview priors"""
        c = Client()
        c.login(username='red', password='red')
        url = reverse('gbd.dismod_data_server.views.dismod_preview_priors', args=[self.dm.id])

        # test get
        response = c.get(url)
        self.assertSuccess(response)
        self.assertPng(response)

        # test post
        response = c.post(url, {'JSON': json.dumps({'smoothing': {'incidence': 'pretty smooth', 'prevalence': 'hello, world'},
                                                    'parameter_age_mesh': [0, 10, 100],
                                                    'y_maximum': 1.0,
                                                    'note': '',
                                                    
                                                    })})
        self.assertSuccess(response)
        self.assertPng(response)
