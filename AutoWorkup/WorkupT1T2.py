#!/usr/bin/python
#################################################################################
## Program:   BRAINS (Brain Research: Analysis of Images, Networks, and Systems)
## Language:  Python
##
## Author:  Hans J. Johnson
##
##      This software is distributed WITHOUT ANY WARRANTY; without even
##      the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
##      PURPOSE.  See the above copyright notices for more information.
##
#################################################################################

import os
import csv
import sys
import string
import argparse
#"""Import necessary modules from nipype."""
#from nipype.utils.config import config
#config.set('logging', 'log_to_file', 'false')
#config.set_log_dir(os.getcwd())
#--config.set('logging', 'workflow_level', 'DEBUG')
#--config.set('logging', 'interface_level', 'DEBUG')
#--config.set('execution','remove_unnecessary_outputs','false')

from nipype.interfaces.base import CommandLine, CommandLineInputSpec, TraitedSpec, File, Directory
from nipype.interfaces.base import traits, isdefined, BaseInterface
from nipype.interfaces.utility import Merge, Split, Function, Rename, IdentityInterface
import nipype.interfaces.io as nio   # Data i/o
import nipype.pipeline.engine as pe  # pypeline engine
from nipype.interfaces.freesurfer import ReconAll

from nipype.utils.misc import package_check
#package_check('nipype', '5.4', 'tutorial1') ## HACK: Check nipype version
package_check('numpy', '1.3', 'tutorial1')
package_check('scipy', '0.7', 'tutorial1')
package_check('networkx', '1.0', 'tutorial1')
package_check('IPython', '0.10', 'tutorial1')

from BRAINSTools import *
from BRAINSTools.ANTSWrapper import *
from BRAINSTools.WarpAllAtlas import *
from BRAINSTools.ants.normalize import WarpImageMultiTransform
from BRAINSTools.ants import antsAverageImages
#BRAINSTools/ants/buildtemplateparallel.py:import antsAverageImages

from WorkupT1T2AtlasNode import MakeAtlasNode


###########################################################################
###########################################################################
###########################################################################
###########################################################################
###########################################################################
###########################################################################
## WorkupT1T2 is the main workflow to be run
###########################################################################
###########################################################################
###########################################################################
###########################################################################
###########################################################################
def WorkupT1T2(subjectid,mountPrefix,ExperimentBaseDirectoryCache, ExperimentBaseDirectoryResults, ExperimentDatabase, atlas_fname_wpath, BCD_model_path,
               InterpolationMode="Linear", Mode=10,DwiList=[],WORKFLOW_COMPONENTS=[],CLUSTER_QUEUE=''):
    """
    Run autoworkup on all subjects data defined in the ExperimentDatabase

    This is the main function to call when processing a data set with T1 & T2
    data.  ExperimentBaseDirectoryPrefix is the base of the directory to place results, T1Images & T2Images
    are the lists of images to be used in the auto-workup. atlas_fname_wpath is
    the path and filename of the atlas to use.
    """

    print "Building Pipeline"
    ########### PIPELINE INITIALIZATION #############
    baw200 = pe.Workflow(name="BAW_20120730")
    baw200.config['execution'] = {
                                     'plugin':'Linear',
                                     #'stop_on_first_crash':'true',
                                     #'stop_on_first_rerun': 'true',
                                     'stop_on_first_crash':'false',
                                     'stop_on_first_rerun': 'false',      ## This stops at first attempt to rerun, before running, and before deleting previous results.
                                     'hash_method': 'timestamp',
                                     'single_thread_matlab':'true',       ## Multi-core 2011a  multi-core for matrix multiplication.
                                     'remove_unnecessary_outputs':'false',
                                     'use_relative_paths':'false',         ## relative paths should be on, require hash update when changed.
                                     'remove_node_directories':'false',   ## Experimental
                                     'local_hash_check':'true',           ##
                                     'job_finished_timeout':15            ##
                                     }
    baw200.config['logging'] = {
      'workflow_level':'DEBUG',
      'filemanip_level':'DEBUG',
      'interface_level':'DEBUG',
      'log_directory': ExperimentBaseDirectoryCache
    }
    baw200.base_dir = ExperimentBaseDirectoryCache


    import WorkupT1T2Single
    MergeT1s=dict()
    MergeT2s=dict()
    MergePosteriors=dict()
    if True:
        print("===================== SUBJECT: {0} ===========================".format(subjectid))
        oneSubjWorkflow=dict()
        subjInfoNode=dict()
        allSessions = ExperimentDatabase.getSessionsFromSubject(subjectid)
        BAtlas = MakeAtlasNode(atlas_fname_wpath,"BAtlas_"+str(subjectid)) ## Call function to create node
        for sessionid in allSessions:
            projectid = ExperimentDatabase.getProjFromSession(sessionid)
            print("PROJECT: {0} SUBJECT: {1} SESSION: {2}".format(projectid,subjectid,sessionid))
            subjInfoNode[sessionid] = pe.Node(interface=IdentityInterface(fields=
                    ['sessionid','subjectid','projectid',
                     'allT1s',
                     'allT2s',
                     'allPDs',
                     'allOthers']),
                    run_without_submitting=True,
                    name='99_SubjInfoNode_'+str(subjectid)+"_"+str(sessionid) )
            subjInfoNode[sessionid].inputs.projectid=projectid
            subjInfoNode[sessionid].inputs.subjectid=subjectid
            subjInfoNode[sessionid].inputs.sessionid=sessionid
            subjInfoNode[sessionid].inputs.allT1s=ExperimentDatabase.getFilenamesByScantype(sessionid,['T1-30','T1-15'])
            subjInfoNode[sessionid].inputs.allT2s=ExperimentDatabase.getFilenamesByScantype(sessionid,['T2-30','T2-15'])
            subjInfoNode[sessionid].inputs.allPDs=ExperimentDatabase.getFilenamesByScantype(sessionid,['PD-30','PD-15'])
            subjInfoNode[sessionid].inputs.allOthers=ExperimentDatabase.getFilenamesByScantype(sessionid,['OTHER-30','OTHER-15'])

            oneSubjWorkflow[sessionid]=WorkupT1T2Single.MakeOneSubWorkFlow(
                              projectid, subjectid, sessionid,
                              BAtlas, WORKFLOW_COMPONENTS,
                              BCD_model_path, InterpolationMode, CLUSTER_QUEUE,
                              ExperimentBaseDirectoryResults)
            baw200.connect(subjInfoNode[sessionid],'projectid',oneSubjWorkflow[sessionid],'InputSpec.projectid')
            baw200.connect(subjInfoNode[sessionid],'subjectid',oneSubjWorkflow[sessionid],'InputSpec.subjectid')
            baw200.connect(subjInfoNode[sessionid],'sessionid',oneSubjWorkflow[sessionid],'InputSpec.sessionid')
            baw200.connect(subjInfoNode[sessionid],'allT1s',oneSubjWorkflow[sessionid],'InputSpec.allT1s')
            baw200.connect(subjInfoNode[sessionid],'allT2s',oneSubjWorkflow[sessionid],'InputSpec.allT2s')
            baw200.connect(subjInfoNode[sessionid],'allPDs',oneSubjWorkflow[sessionid],'InputSpec.allPDs')
            baw200.connect(subjInfoNode[sessionid],'allOthers',oneSubjWorkflow[sessionid],'InputSpec.allOthers')
        if True: ## Merge all BCD_Results into a global average
            numSessions=len(allSessions)
            mergeSubjectSessionNamesT1="99_MergeAllSessions_T1"+str(subjectid)
            MergeT1s[subjectid] = pe.Node(interface=Merge(numSessions),
                                          run_without_submitting=True,
                                          name=mergeSubjectSessionNamesT1)
            mergeSubjectSessionNamesT2="99_MergeAllSessions_T2"+str(subjectid)
            MergeT2s[subjectid] = pe.Node(interface=Merge(numSessions),
                                          run_without_submitting=True,
                                          name=mergeSubjectSessionNamesT2)
            mergeSubjectSessionNamesPosteriors="99_MergeAllSessions_Posteriors"+str(subjectid)
            MergePosteriors[subjectid] = pe.Node(interface=Merge(numSessions),
                                          run_without_submitting=True,
                                          name=mergeSubjectSessionNamesPosteriors)
            index=1
            #print("HACK: HACK: HACK:  {0}".format(allSessions))
            for sessionid in allSessions:
                index_name='in'+str(index)
                index+=1
                baw200.connect(oneSubjWorkflow[sessionid],'OutputSpec.t1_average',MergeT1s[subjectid],index_name)
                baw200.connect(oneSubjWorkflow[sessionid],'OutputSpec.t2_average',MergeT2s[subjectid],index_name)
                baw200.connect(oneSubjWorkflow[sessionid],'OutputSpec.posteriorImages',MergePosteriors[subjectid],index_name)

            def MergeByExtendListElements(t2_averageList,posteriorImagesList):
                """ The posteriorImagesList must have an even multiple of 
                   images in the list.
                    a=['a','a','b','b','c','c']
                    b=['1','2','3']
                    output=[['1','a','a'],['2','b','b'],['3','c','c']]
                """
                mergedList=list()
                repeatNumbers=len(posteriorImagesList)/len(t2_averageList)
                posterior_index=0
                for t2_index in range(0,len(t2_averageList)):
                    this_subj_list=list()
                    this_subj_list.append(t2_averageList[t2_index])
                    for i in range(0,repeatNumbers):
                        this_subj_list.append(posteriorImagesList[posterior_index])
                        posterior_index+=1
                    mergedList.append(this_subj_list)
                return mergedList
            MergeByExtendListElementsNode = pe.Node( Function(function=MergeByExtendListElements,
                                          input_names = ['t2_averageList','posteriorImagesList'],
                                          output_names = ['mergedList']),
                                          run_without_submitting=True, name="99_MergeByExtendListElements")
            MergeByExtendListElementsNode.inputs.preserve_nested_lists = True
            baw200.connect( MergeT2s[subjectid],'out', MergeByExtendListElementsNode, 't2_averageList' )
            baw200.connect( MergePosteriors[subjectid],'out', MergeByExtendListElementsNode, 'posteriorImagesList' )

            """ Now part of ants directly
            InitAvgImages=pe.Node(interface=antsAverageImages.AntsAverageImages(), name ='InitBCDAvgImages_'+str(subjectid))
            InitAvgImages.inputs.dimension = 3
            InitAvgImages.inputs.output_average_image = str(subjectid)+"_TissueClassAVG_T1.nii.gz"
            InitAvgImages.inputs.normalize = 1
            baw200.connect(MergeT1s[subjectid], 'out', InitAvgImages, 'images')
            """
            from BRAINSTools.ants.antsSimpleAverageWF import antsSimpleAverageWF
            ### USE ANTS
            from BRAINSTools.ants.buildtemplateparallel import ANTSTemplateBuildSingleIterationWF
            ### USE ANTS REGISTRATION
            #from BRAINSTools.ants.buildtemplateparallel_antsRegistration import antsRegistrationTemplateBuildSingleIterationWF

            myInitAvgWF = antsSimpleAverageWF()
            baw200.connect(MergeT1s[subjectid], 'out', myInitAvgWF, 'InputSpec.images')

            buildTemplateIteration1 = ANTSTemplateBuildSingleIterationWF('Iteration01',CLUSTER_QUEUE)
            baw200.connect(myInitAvgWF, 'OutputSpec.average_image', buildTemplateIteration1, 'InputSpec.fixed_image')
            baw200.connect(MergeT1s[subjectid], 'out', buildTemplateIteration1, 'InputSpec.images')
            baw200.connect(MergeByExtendListElementsNode, 'mergedList', buildTemplateIteration1, 'InputSpec.passive_images_list')

            #buildTemplateIteration2 = buildTemplateIteration1.clone(name='buildTemplateIteration2')
            buildTemplateIteration2 = ANTSTemplateBuildSingleIterationWF('Iteration02',CLUSTER_QUEUE)
            baw200.connect(buildTemplateIteration1, 'OutputSpec.template', buildTemplateIteration2, 'InputSpec.fixed_image')
            baw200.connect(MergeT1s[subjectid], 'out', buildTemplateIteration2, 'InputSpec.images')
            baw200.connect(MergeByExtendListElementsNode, 'mergedList', buildTemplateIteration2, 'InputSpec.passive_images_list')

            #baw200.connect(InitAvgImages, 'average_image', outputSpec, 'average_image')

    return baw200
