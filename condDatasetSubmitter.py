#! /usr/bin/env python

from __future__ import print_function
import ast
import os
import sys
import re
import datetime

from optparse import OptionParser

sys.path.append('/afs/cern.ch/cms/PPD/PdmV/tools/prod/devel/')
from phedex import phedex
from modules import wma

DRYRUN = False # pass option --dry to set to true

dfile = open("cmsDrivers.sh", "w")
dfile.write("#!/bin/bash \nset -x\n")

#-------------------------------------------------------------------------------

def createOptionParser():
    global DRYRUN
    usage = \
    """
    ConditionValidation.py --gt <GT> [ either: --run <run> or: --runLs <runLumiDict>] --conds <condition json>
    """

    parser = OptionParser(usage)
    parser.add_option("--jira",
                        dest="jira",
                        help="jira ticket, where validation will take place")
    parser.add_option("--newgt",
                        dest="newgt",
                        help="new global tag containing tag to be tested")
    parser.add_option("--gt",
                        dest="gt",
                        help="common/reference global tag to both submissions")
    parser.add_option("--basegt",
                        dest="basegt",
                        default="",
                        help="common global tag to base RECO+HLT/HLT+RECO submissions")
    parser.add_option("--run",
                        help="the run number to be processed, can be a comma separated list")
    parser.add_option("--runLs",
                        help="the dictionary of run numbers mapped to lists of lumi sections (standard CMS certification json format)")
    parser.add_option("--ds",
                        help="dataset to be processed",
                        default="/MinimumBias/Run2012B-PromptReco-v1/RECO")
    parser.add_option("--conds",
                        help="List of new tag,record,connection_string triplets to be tested")
    parser.add_option("--dry",
                        default=False,
                        action='store_true')
    parser.add_option("--Type",
                        help="Defines the type of the workflow",
                        choices=['HLT','PR','PR+ALCA', 'EXPR', 'RECO+HLT','HLT+RECO', 'EXPR+RECO', 'HLT+RECO+ALCA'],
                        default='HLT')
    parser.add_option("--two_WFs",
                        default=False,
                        help="Creates two workflows for type PR if HLT+RECO workflows are not created initially",
                        action="store_true")
    parser.add_option("--HLT",
                        help="Specify which default HLT menu: SameAsRun uses the HLT menu corrresponding to the run, Custom lets you choose it explicitly",
                        choices=['SameAsRun','GRun','50nsGRun','Custom','25ns14e33_v3'],
                        default=None)
    parser.add_option("--B0T",
                        default=False,
                        help="Specify 0T reconstruction",
                        action='store_true')
    parser.add_option("--cosmics",
                        default=False,
                        help="Specify HIon reconstruction",
                        action='store_true')
    parser.add_option("--HIon",
                        default=False,
                        help="Specify HIon reconstruction",
                        action='store_true')
    parser.add_option("--pA",
                        default=False,
                        help="Specify pA reconstruction",
                        action='store_true')
    parser.add_option("--HLTCustomMenu",
                        help="Specify a custom HLT menu",
                        default=None)
    parser.add_option("--string",
                        help="Processing string to add to dataset name (default is current date)",
                        default=None)
    parser.add_option("--recoCmsswDir",
                        help="CMSSW base directory for RECO step if different from HLT step (supported for HLT+RECO type)",
                        default=None)
    parser.add_option("--noSiteCheck",
                        help="Prevents the site check to be operated",
                        default=False,
                        action='store_true')

    (options,args) = parser.parse_args()

    if not options.newgt or not options.gt or not (options.run or options.runLs):
        parser.error("options --newgt, --run, [ either: --run  or: --runLs ] and --gt  are mandatory")

    if (options.runLs):
        options.runLs = ast.literal_eval(options.runLs)


    CMSSW_VERSION = 'CMSSW_VERSION'
    if CMSSW_VERSION not in os.environ:
        print("\n CMSSW not properly set. Exiting")
        sys.exit(1)

    options.release = os.getenv(CMSSW_VERSION)

    CMSSW_BASE = 'CMSSW_BASE'
    options.hltCmsswDir = os.getenv(CMSSW_BASE)

    options.recoRelease = None
    if options.recoCmsswDir:
        options.recoRelease = getCMSSWReleaseFromPath(options.recoCmsswDir)
    else:
        options.recoRelease = getCMSSWReleaseFromPath(options.hltCmsswDir)
        # if a release is not provided for the reco step (RECO or PR), use the only release known hltCmsswDir

    if options.dry:
        DRYRUN = True

    options.ds = options.ds.split(',')
    if (options.run):
        options.run = options.run.split(',')

    return options

#-------------------------------------------------------------------------------

def getConfCondDictionary(conditions_filename):
    ConfCondList = [('REFERENCE.py', options.gt)]
    ConfCondDictionary = {'REFERENCE.py':options.gt}

    ConfCondDictionary['NEWCONDITIONS0.py'] = options.newgt
    ConfCondList.append(('NEWCONDITIONS0.py', options.newgt))
    #return ConfCondDictionary
    return ConfCondList

#-------------------------------------------------------------------------------

def isPCLReady(run):
    ##TO-DO: do we need this commented out code?
    #mydict = json.loads(os.popen('curl -L --cookie ~/private/ssocookie.txt --cookie-jar ~/private/ssocookie.txt https://cms-conddb-prod.cern.ch/pclMon/get_latest_runs?run_class=Cosmics% -k').read())

    #print mydict
    # for line in os.popen('curl -s http://cms-alcadb.web.cern.ch/cms-alcadb/Monitoring/PCLTier0Workflow/log.txt').read().split('\n'):
    #     if not line: continue
    #     spl = line.split()
    #     if spl[0] == str(run):
    #         ready = ast.literal_eval(spl[7])
    #         print "\n\n\tPCL ready for ",run,"\n\n"
    #         return ready

    return False

def isAtSite(ds, run):
    blocks = []
    ph = phedex(ds)
    # get list of blocks for input dataset directly from DBS3
    # documentation: https://cmsweb.cern.ch/dbs/prod/global/DBSReader/
    connection = wma.init_connection('cmsweb.cern.ch')
    #returns a string which represents a list, so we have to eval
    blockDicts = ast.literal_eval(
            wma.httpget(connection, wma.DBS3_URL + "blocks?dataset=%s&run_num=%s" % (ds, run)))

    for blockDict in blockDicts:
        block = blockDict['block_name']
        # print "block is: %s"%block

          # it's unclear what probing custodiality means; remove this check
          #
          # for b in filter(lambda b :b.name==block,ph.block):
          #     for replica in filter(lambda r : r.custodial=='y',b.replica):
          #         if replica.complete!='y':
          #             print block,'not complete at custodial site'
          #             #print block,'not complete at custodial site but ignoring'
          #             #blocks.append('#'+block.split('#')[-1])
          #         else:
          #             print block,'complete at custodial site'
          #             blocks.append('#'+block.split('#')[-1])

        blocks.append('#' + block.split('#')[-1])

    if len(blocks) == 0:
        print("No possible block for %s in %s" % (run, ds))
        return False
    else:
        print("\n\n\t Block testing succeeded for %s in %s \n\n" % (run, ds))
        print(blocks)
        return list(set(blocks))

#-------------------------------------------------------------------------------

# we need this check to handle the discontinued customise functions
def isCMSSWBeforeEight(theRelease):
    if theRelease == None:
        raise ValueError('theRelease is set to %s and yet, it seems to be required. ERRROR.' % (theRelease))
    if int(theRelease.split("_")[1]) < 8:
        return True
    elif int(theRelease.split("_")[1]) == 8:
        return int(theRelease.split("_")[2]) < 1  and int(theRelease.split("_")[3]) < 1
    else:
        return False

def is_hltGetConfigurationOK (theRelease):
    if theRelease == None:
        raise ValueError('theRelease is set to %s and yet, it seems to be required. ERRROR.' % (theRelease))
    if int(theRelease.split("_")[1]) > 8:
        return True
    if int(theRelease.split("_")[1]) == 8:
        return int(theRelease.split("_")[2]) < 1  and int(theRelease.split("_")[3]) >= 9
    else:
        return False

def getCMSSWReleaseFromPath(thePath):
    path_list = thePath.split('/')
    for path in path_list:
        if path.find("CMSSW") != -1:
            return path
    raise ValueError('%s does not contain a slash-separated path to a CMSSW release. ERRROR.' % (thePath))

def getDriverDetails(Type, release, ds, B0T, HIon, pA, cosmics, recoRelease):
    str_era_hlt = 'Run2_2018'
    if release.find("10_")!= -1:
        for ds_name in ds:
            if ds_name.find("2018")!=-1:
                str_era_hlt="Run2_2018"
    if release.find("11_")!= -1:
        for ds_name in ds:
            if ds_name.find("2021")!=-1:
                str_era_hlt="Run3"
    if release.find("12_")!= -1:
        for ds_name in ds:
            if ds_name.find("2021")!=-1:
                str_era_hlt="Run3"

    str_era_pr="Run2_2018"
    if recoRelease.find("10_")!= -1:
        for ds_name in ds:
            if ds_name.find("2018")!=-1:
                str_era_pr="Run2_2018"
    if recoRelease.find("11_")!= -1:
        for ds_name in ds:
            if ds_name.find("2021")!=-1:
                str_era_pr="Run3"
    if recoRelease.find("12_")!= -1:
        for ds_name in ds:
            if ds_name.find("2021")!=-1:
                str_era_pr="Run3"

    HLTBase = {"reqtype":"HLT",
                "steps":"L1REPACK:Full,HLT,DQM", #replaced DQM:triggerOfflineDQMSource with DQM
                "procname":"HLT2",
                "datatier":"FEVTDEBUGHLT,DQM ",
                "eventcontent":"FEVTDEBUGHLT,DQM",
                "inputcommands":'keep *,drop *_hlt*_*_HLT,drop *_TriggerResults_*_HLT,drop *_*_*_RECO',
                "era":str_era_hlt,
                #"custcommands":'process.schedule.remove( process.HLTriggerFirstPath )',
                "custcommands":"process.load('Configuration.StandardSequences.Reconstruction_cff'); " +\
                               "process.hltTrackRefitterForSiStripMonitorTrack.src = 'generalTracks'; ",
                "custconditions":"JetCorrectorParametersCollection_CSA14_V4_MC_AK4PF,JetCorrectionsRecord,frontier://FrontierProd/CMS_CONDITIONS,AK4PF",
                "magfield":"",
                "dumppython":False,
                "inclparents":"True"}

    if B0T:
        HLTBase.update({"magfield":"0T"})    # this should not be needed - it's GT-driven FIX GF

    if cosmics:
        HLTBase.update({"datatier":"FEVTDEBUG,DQM", "eventcontent":"FEVTDEBUG,DQM"})
        
    if pA:
        HLTBase.update({"era":"Run3_2022_pA"})

    HLTRECObase = {"steps":"RAW2DIGI,L1Reco,RECO",
                    "procname":"reRECO",
                    "datatier":"RAW-RECO", # why RAW-RECO here while RECO elsewhere ?
                    "eventcontent":"RAWRECO",
                    "inputcommands":'',
                    "custcommands":''}

    if options.HLT:
        HLTBase.update({"steps":"L1REPACK,HLT:%s,DQM" % (options.HLT),
                "dumppython":False})

    if Type == 'HLT':
        return HLTBase
    elif Type == 'RECO+HLT':
        HLTBase.update({'base':HLTRECObase})
        return HLTBase
    elif Type in ['HLT+RECO','HLT+RECO+ALCA', 'EXPR+RECO']:
        if options.HLT:
            HLTBase.update({"steps":"L1REPACK,HLT:%s" % (options.HLT),
                            "custcommands": "",
                            "custconditions":"",
                            #"output":'[{"e":"RAW","t":"RAW","o":["drop FEDRawDataCollection_rawDataCollector__LHC"]}]',
                            "output":'',
                            #"datatier":"RAW",
                            #"eventcontent":"RAW",
                            "dumppython":False,
                            "lumiToProcess":"step1_lumi_ranges.txt"})

        else:
            HLTBase.update({"steps":"L1REPACK,HLT",
                            "custcommands":"",
                            "custconditions":"",
                            #"datatier":"RAW",
                            #"eventcontent":"RAW",
                            "magfield":""})

        if Type == 'EXPR+RECO': HLTBase.update({'reqtype': 'EXPRESS'})
        HLTRECObase = {"steps":"RAW2DIGI,L1Reco,RECO,EI,PAT,DQM:DQMOffline+offlineValidationHLTSource",
                        "procname":"reRECO",
                        "datatier":"RECO,DQMIO",
                        "eventcontent":"RECO,DQM",
                        #"inputcommands":'keep *',
                        "inputcommands":'',
                        "custcommands":'',
                        "custconditions":'',
                        "customise":'',
                        "era":str_era_hlt,
                        "runUnscheduled": None,
                        "magfield":"",
                        "dumppython":False}

        # keep backward compatibility with releases earlier than 8_0_x

        if isCMSSWBeforeEight(recoRelease):
            raise ValueError('theRelease is set to %s, which is not supported by condDatasetSubmitter' % (recoRelease))

        if B0T:
            HLTRECObase.update({"magfield":"0T"})

        if cosmics: 
            HLTRECObase.update({"steps":"RAW2DIGI,L1Reco,RECO,DQM"})
            if Type == "EXPR+RECO":
                HLTRECObase.update({"customise":"Configuration/DataProcessing/RecoTLR.customiseExpress,Configuration/DataProcessing/RecoTLR.customiseCosmicData"})

        if pA:
            HLTRECObase.update({"era":"Run3_2022_pA"})

        if HIon:
            raise ValueError('condDatasetSubmitter is not yet set up to run HI validations - e-tutto-lavoraccio')

        if Type == 'HLT+RECO+ALCA':
            HLTRECObase.update({"steps":"RAW2DIGI,L1Reco,RECO,ALCA:SiStripCalMinBias,DQM"})

        HLTBase.update({'recodqm':HLTRECObase})
        return HLTBase

    elif Type in ['PR', 'PR+ALCA', 'EXPR']:
        theDetails = {"reqtype":"PR",
                        "steps":"RAW2DIGI,L1Reco,RECO,EI,PAT,DQM",
                        "procname":"reRECO",
                        "datatier":"RECO,DQMIO ",
                        "output":'',
                        "eventcontent":"RECO,DQM",
                        #"inputcommands":'keep *',
                        "inputcommands":'',
                        "custcommands":'',
                        "custconditions":'',
                        "customise":'',
                        "era":str_era_pr,
                        "runUnscheduled": None,
                        "magfield":"",
                        "lumiToProcess":"step1_lumi_ranges.txt",
                        "dumppython":False,
                        "inclparents":"False"}

        if isCMSSWBeforeEight(recoRelease):
            raise ValueError('theRelease is set to %s, which is not supported by condDatasetSubmitter' % (recoRelease))

        if B0T:
            theDetails.update({"magfield":"0T"})

        if cosmics:
            theDetails.update({"steps": "RAW2DIGI,L1Reco,RECO,DQM"})
            if Type == 'PR':
                theDetails.update({"customise":"Configuration/DataProcessing/RecoTLR.customisePrompt,Configuration/DataProcessing/RecoTLR.customiseCosmicData"})
            if Type == 'EXPR':
                theDetails.update({"customise":"Configuration/DataProcessing/RecoTLR.customiseExpress,Configuration/DataProcessing/RecoTLR.customiseCosmicData"})

        if pA:
            theDetails.update({"era":"Run2_2016_pA"})

        if HIon:
            raise ValueError('condDatasetSubmitter is not yet set up to run HI validations - e-tutto-lavoraccio')
            # WHICH ERA HERE ???

        if Type == 'PR+ALCA':
            theDetails.update({"steps":"RAW2DIGI,L1Reco,RECO,ALCA:SiStripCalMinBias,DQM"})

        if Type == 'EXPR':
            theDetails.update({"reqtype":"EXPR"})

        return theDetails

#-------------------------------------------------------------------------------
def step1(options):
    """Collect list of input files, needed for dry run"""
    dfile.write("\n# Step1: create list of input files\n")
    run = options.run[0] if options.run else str(options.runLs).split(":")[0].strip("{u").strip("'")
    value2 = None if options.run else list(options.runLs.items())[0][1]
    command1 = "echo '' > step1_files.txt\n"
    execme(command1, echo=False)
    for dataset in options.ds:
        dasgo0 = "dasgoclient --limit 10 --format json --query 'lumi,file dataset={} run={}'"
        if options.runLs:
            dasgo = dasgo0 + " | das-selected-lumis.py {} | sort -u >> step1_files.txt\n"
            execme(dasgo.format(dataset, run, "%s,%s"%(value2[0][0],value2[0][1]) ), echo=False)
        else:
            dasgo = "dasgoclient --limit 10 --format list --query 'file dataset={} run={}' >> step1_files.txt"
            execme(dasgo.format(dataset, run), echo=False)
    if options.runLs:
        command3 = 'echo \'{}\' > step1_lumi_ranges.txt\n'.format("{\""+run+"\": %s}"%(value2))
        execme(command3, echo=False)

def splitOptions(command, echo = True):
    if echo: dfile.write("\n")
    if "hltGetConfiguration" in command:
        dfile.write("# Step 0: Extract custom HLT configuration from given HLT menu\n")
    if "--processName HLT2" in command:
        dfile.write("# Step 2: HLT\n")
    if "--processName reRECO" in command:
        dfile.write("# Step 3: Reconstruction\n")
    if "step4" in command:
        dfile.write("# Step 4: DQM Harvesting\n")
    for cmd in command.split(";"):
        if 'cmsDriver' in cmd:
            for idx, ccc in zip(range(len(cmd.split('--'))), cmd.split('--')):
                dfile.write("# "+ccc+"\n") if idx==0 else dfile.write("# --"+ccc+"\n")
        elif echo:
            dfile.write("# "+cmd+"\n")
    if echo:
        dfile.write("\n"+command+"\n")
    else:
        dfile.write(command+"\n")

def execme(command, echo = True):
    if DRYRUN:
        print(command)
        if not 'wmcontrol' in command: splitOptions(command, echo=echo)
    else:
        print(" * Executing: %s..." % command)
        splitOptions(command, echo=echo)
        os.system(command)
        print(" * Executed!")

#-------------------------------------------------------------------------------
def collect_commands(options):
    command = []
    command.append("export SCRAM_ARCH=slc7_amd64_gcc900")
    command.append("scramv1 project %s" %(options.release))
    command.append("cd %s/src" %(options.release))
    command.append("eval `scramv1 runtime -sh`")
    command.append("git cms-addpkg HLTrigger/Configuration")
    command.append("scramv1 b")
    command.append("cd -")
    if DRYRUN: 
        for cmd in command: execme(cmd, echo = False)

def createHLTConfig(options):
    assert os.path.exists("%s/src/HLTrigger/Configuration/" % (options.hltCmsswDir)), "error: HLTrigger/Configuration/ is missing in the CMSSW release for HLT (set to: echo $CMSSW_VERSION ) - can't create the HLT configuration "
    onerun = 0

    if (options.run):
        onerun = options.run[0]
    elif (options.runLs):
        onerun = options.runLs.keys()[0]

    if options.HLT == "SameAsRun":
        hlt_command = "hltGetConfiguration --unprescale --cff --offline " +\
                    "run:%s " % onerun +\
                    "> %s/src/HLTrigger/Configuration/python/HLT_%s_cff.py" % (options.hltCmsswDir, options.HLT)

    elif options.HLT == "Custom":
        hlt_command = "hltGetConfiguration --unprescale --cff --offline " +\
                    "%s " % options.HLTCustomMenu +\
                    "> %s/src/HLTrigger/Configuration/python/HLT_%s_cff.py" % (options.hltCmsswDir, options.HLT)

    cmssw_command = "cd %s; eval `scramv1 runtime -sh`; cd -" % options.hltCmsswDir
    build_command = "cd %s/src; eval `scramv1 runtime -sh`; scram b; cd -" % (options.hltCmsswDir)

    patch_command = "sed -i 's/+ fragment.hltDQMFileSaver//g' %s/src/HLTrigger/Configuration/python/HLT_%s_cff.py" % (options.hltCmsswDir, options.HLT)
    patch_command2 = "sed -i 's/, fragment.DQMHistograms//g' %s/src/HLTrigger/Configuration/python/HLT_%s_cff.py" % (options.hltCmsswDir, options.HLT)

    if (is_hltGetConfigurationOK(getCMSSWReleaseFromPath(options.hltCmsswDir))):
        # execme(cmssw_command + '; ' + hlt_command + '; ' + build_command)
        execme(hlt_command)
    else:
        execme(cmssw_command + '; ' + hlt_command + '; ' + patch_command + '; ' + patch_command2 + '; ' + build_command)
        print("\n CMSSW release for HLT doesn't allow usage of hltGetConfiguration out-of-the-box, patching configuration ")

def createCMSSWConfigs(options,confCondDictionary,allRunsAndBlocks):
    details = getDriverDetails(options.Type, options.release, options.ds, options.B0T, options.HIon,options.pA, options.cosmics, options.recoRelease)
    # get processing string
    if options.string is None:
        processing_string = str(datetime.date.today()).replace("-", "_") + "_" + str(datetime.datetime.now().time()).replace(":", "_")[0:5]
    else:
        processing_string = options.string # GF: check differentiation between steps VS step{2}_processstring

    scenario = '--scenario pp'
    if options.HIon:
        scenario = '--scenario HeavyIons --repacked'
    if options.cosmics:
        scenario = '--scenario cosmics'

    # Create the drivers
    for cfgname, custgt in confCondList:
        dfile.write("\n##### Steps for %s conditions!!" %('NEW' if 'NEW' in cfgname.strip('.py').strip('0') else cfgname.strip('.py').strip('0')))
        print("\n\n\tCreating for", cfgname, "\n\n")
        driver_command = "cmsDriver.py %s " % (details['reqtype'])+\
                "-s %s " % (details['steps']) +\
                "--processName %s " % (details['procname']) +\
                "--data %s " % (scenario) +\
                "--datatier %s " % (details['datatier']) +\
                "--conditions %s " % (custgt) +\
                "--python_filename %s " % (cfgname) +\
                "--filein '%s' " % ("filelist:step1_files.txt") +\
                "--fileout '%s' " % ("file:step2.root") +\
                "--no_exec " +\
                "-n 100 "

        if details['eventcontent']:
            driver_command += "--eventcontent %s " % (details['eventcontent'])
        if details['output'] != '':
            driver_command += "--output '%s' " % (details['output'])
        if details['dumppython']:
            driver_command += "--dump_python "
        if 'customise' in details.keys() and details['customise'] != '':
            driver_command += '--customise %s ' % (details['customise'])
        if details['era'] != "":
            driver_command += "--era %s " % (details['era'])
        if options.Type in ['PR', 'PR+ALCA']:
            if details['runUnscheduled'] == "":
                driver_command += "--runUnscheduled "
        if details['magfield'] != "":
            driver_command += '--magField %s ' % (details['magfield'])
        if details['lumiToProcess'] != "" and options.runLs:
            driver_command += "--lumiToProcess 'step1_lumi_ranges.txt' "
        if details['inputcommands'] != "":
            driver_command += '--inputCommands "%s" ' % (details['inputcommands'])
        if details['custconditions'] != "":
            driver_command += '--custom_conditions="%s" ' % (details['custconditions'])
        if details['custcommands'] != "":
            driver_command += "--customise_commands='%s' " % (details['custcommands'])

        #Temporary changes
        driver_command += '--customise "Configuration/DataProcessing/RecoTLR.customisePostEra_Run3" '
        # ---------

        cmssw_command = "cd %s; eval `scramv1 runtime -sh`; cd -" % (options.hltCmsswDir)
        upload_command = "./wmupload.py -u %s -g PPD -l %s %s"% (os.getenv('USER'), cfgname, cfgname)
        if ('NEW' in cfgname and options.recoCmsswDir):
            execme(cmssw_command + '; ' + driver_command)  
        else: 
            execme(driver_command)
        upload_command = "" #if DRYRUN else execme(upload_command)
        base = None

        if 'base' in details:
            base = details['base']
            driver_command = "cmsDriver.py %s " % (details['reqtype'])+\
                            "-s %s " % (base['steps']) +\
                            "--processName %s " % (base['procname']) +\
                            "--data %s " % (scenario) +\
                            "--datatier %s " % (base['datatier']) +\
                            "--eventcontent %s " % (base['eventcontent']) +\
                            "--conditions %s " % (options.basegt) +\
                            "--python_filename reco.py " +\
                            "--no_exec " +\
                            "-n 100 "

            execme(driver_command)

        label = cfgname.lower().replace('.py', '')[0:5]
        recodqm = None
        if 'recodqm' in details:
            recodqm = details['recodqm']
            driver_command = "cmsDriver.py %s " % (details['reqtype']) +\
                            "-s %s " % (recodqm['steps']) +\
                            "--processName %s " % (recodqm['procname']) +\
                            "--data %s " % (scenario) +\
                            "--datatier %s " % (recodqm['datatier']) +\
                            "--eventcontent %s " % (recodqm['eventcontent']) +\
                            "--conditions %s " % (options.basegt) +\
                            "--hltProcess HLT2 " +\
                            "--filein=file:step2.root " +\
                            "--fileout=file:step3.root " +\
                            "--python_filename recodqm_%s.py "% (label) +\
                            "--no_exec " +\
                            "-n 100 "

            if 'customise' in recodqm.keys() and recodqm['customise'] != "":
                driver_command += "--customise %s " % (recodqm['customise'])
            if recodqm['era'] != "":
                driver_command += "--era %s " % (recodqm['era'])
            if recodqm['runUnscheduled'] == "":
                driver_command += "--runUnscheduled "
            if recodqm['dumppython']:
                driver_command += "--dump_python "
            if recodqm['magfield'] != "":
                driver_command += "--magField %s " % (recodqm['magfield'])
            if recodqm['custcommands'] != "":
                driver_command += "--customise_commands='%s' " % (recodqm['custcommands'])

            #Temporary changes
            driver_command += '--customise "Configuration/DataProcessing/RecoTLR.customisePostEra_Run3" '
            # ---------

            if options.recoCmsswDir:
                cmssw_command = "cd %s; eval `scramv1 runtime -sh`; cd -" % (options.recoCmsswDir)
                upload_command = "./wmupload.py -u %s -g PPD -l %s %s" % (os.getenv('USER'),
                        'recodqm.py', 'recodqm.py')
                execme(cmssw_command + '; ' + driver_command)
                upload_command = "" #if DRYRUN else execme(upload_command)
            else:
                execme(driver_command)

            if options.Type.find("ALCA") != -1:
                filein = "%s_RAW2DIGI_L1Reco_RECO_ALCA_DQM_inDQM.root" % (details['reqtype'])
            else:
                filein = "step3_inDQM.root"

            driver_command = "cmsDriver.py step4 " +\
                            "-s HARVESTING:dqmHarvesting " +\
                            "--data %s " % (scenario) +\
                            "--filetype DQM " +\
                            "--conditions %s " % (options.basegt) +\
                            "--filein=file:%s " % (filein) +\
                            "--fileout=file:step4.root " +\
                            "--python_filename=step4_%s_HARVESTING.py " % (label) +\
                            "--no_exec " +\
                            "-n 100 "

            if recodqm['era'] != "":
                driver_command += "--era %s " % (recodqm['era'])
            if options.recoCmsswDir:
                cmssw_command = "cd %s; eval `scramv1 runtime -sh`; cd -" % (options.recoCmsswDir)
                upload_command = "./wmupload.py -u %s -g PPD -l %s %s" % (os.getenv('USER'),
                        'step4_%s_HARVESTING.py' % label,'step4_%s_HARVESTING.py' % label)
                execme(cmssw_command + '; ' + driver_command)
                upload_command = "" #if DRYRUN else execme(upload_command)
            else:
                execme(driver_command)
        else:
            if options.Type.find("ALCA") != -1:
                filein = "%s_RAW2DIGI_L1Reco_RECO_ALCA_DQM_inDQM.root" % (details['reqtype'])
            else:
                #filein = "%s_RAW2DIGI_L1Reco_RECO_DQM_inDQM.root" % (details['reqtype'])
                filein = "step2_inDQM.root"

            driver_command = "cmsDriver.py step4 " +\
                            "-s HARVESTING:dqmHarvesting " +\
                            "--data %s " % (scenario) +\
                            "--filetype DQM " +\
                            "--conditions %s " % (custgt) +\
                            "--filein=file:%s " % (filein) +\
                            "--python_filename=step4_%s_HARVESTING.py " % (label) +\
                            "--no_exec " +\
                            "-n 100 "
            if details['era'] != "":
                driver_command += "--era %s " % (details['era'])
            execme(driver_command)
    ##END of for loop

    matched = re.match("(.*),(.*),(.*)", options.newgt)
    if matched:
        gtshort = matched.group(1)
    else:
        gtshort = options.newgt

    matched = re.match("(.*),(.*),(.*)", options.gt)
    if matched:
        refgtshort = matched.group(1)
    else:
        refgtshort = options.gt

    if base:
        subgtshort = gtshort
        refsubgtshort = refgtshort
        matched = re.match("(.*),(.*),(.*)", options.basegt)
        if matched:
            gtshort = matched.group(1)
        else:
            gtshort = options.basegt

    if recodqm:
        subgtshort = gtshort
        refsubgtshort = refgtshort
        matched = re.match("(.*),(.*),(.*)",options.basegt)
        if matched:
            gtshort = matched.group(1)
        else:
            gtshort = options.basegt

    # Creating the WMC cfgfile
    wmcconf_text = '[DEFAULT] \n'+\
                    'group=ppd \n'+\
                    'user=%s\n' % (os.getenv('USER'))

    if base or recodqm:
        wmcconf_text += 'request_type= TaskChain \n'
    else:
        wmcconf_text += 'request_type= TaskChain \n'#+\
                  # 'includeparents = %s \n' %details['inclparents']

    if recodqm:
        wmcconf_text += 'priority = 900000 \n'+\
                        'release=%s\n' % (options.release) +\
                        'globaltag =%s \n' % (subgtshort)
    else:
        wmcconf_text += 'priority = 900000 \n'+\
                        'release=%s\n' % (options.release) +\
                        'globaltag =%s \n' % (gtshort)

    wmcconf_text += 'campaign=%s__ALCA_%s-%s\n' % (options.release,options.jira,datetime.datetime.now().strftime("%Y_%m_%d_%H_%M")) +\
                    'acquisition_era=%s\n' % (options.release)

    """
    for ds in options.ds:
        # if options.run is not specified and runLs is, simply leave the list of runs blank
        if (options.run):
            wmcconf_text += '"%s" : [%s],\n ' % (ds,
                    ','.join(options.run + map(lambda s :'"%s"' % (s), allRunsAndBlocks[ds])))

        else:
            wmcconf_text += '"%s" : [],\n ' % (ds)
    wmcconf_text += '}\n'
    """
    onerun = 0
    if (options.run):
        onerun = options.run[0]
    elif (options.runLs):
        onerun = options.runLs.keys()[0]

    # lumi_list is set as a general parameter,
    # under the assumption that all workflows need be run on the same set of events
    if (options.runLs):
        wmcconf_text += 'lumi_list=%s\n' % (options.runLs)

    wmcconf_text+='multicore=4\n'
    wmcconf_text += 'enableharvesting = True\n'
    wmcconf_text += 'dqmuploadurl = https://cmsweb.cern.ch/dqm/relval\n'
    wmcconf_text += 'subreq_type = RelVal\n\n'

    if base:
        wmcconf_text += '[HLT_validation]\n'+\
                        'cfg_path = reco.py\n' +\
                        'req_name = %s_RelVal_%s\n' % (details['reqtype'], onerun) +\
                        '\n\n'
    elif recodqm:
        pass
    else:
        for ds in options.ds :
            ds_name = ds[:1].replace("/","") + ds[1:].replace("/","_")
            ds_name = ds_name.replace("-","_")
            label   = cfgname.lower().replace('.py', '')[0:5]
            wmcconf_text += '[%s_reference_%s]\n' % (details['reqtype'],ds_name) +\
                            'input_name = %s\n' % (ds) +\
                            'request_id = %s__ALCA_%s-%s_%s_%srefer\n' % (options.release,options.jira,datetime.datetime.now().strftime("%Y_%m_%d_%H_%M"),ds_name, details['reqtype']) +\
                            'keep_step1 = True\n' +\
                            'time_event = 10\n' +\
                            'size_memory = 8000\n' +\
                            'step1_lumisperjob = 1\n' +\
                            'processing_string = %s_%sref_%s \n' % (processing_string, details['reqtype'], refgtshort) +\
                            'cfg_path = REFERENCE.py\n' +\
                            'req_name = %s_reference_RelVal_%s\n' % (details['reqtype'], onerun) +\
                            'globaltag = %s\n' % (refgtshort) +\
                            'harvest_cfg=step4_refer_HARVESTING.py\n\n' # this is ugly and depends on [0:5]; can't be easliy fixed w/o reorganization

    task = 2
    print(confCondList)
    for (i, c) in enumerate(confCondList):
        cfgname = c[0]
        if "REFERENCE" in cfgname:
            if base:
                wmcconf_text += 'step%d_output = RAWRECOoutput\n' % (task) +\
                    'step%d_cfg = %s\n' % (task, cfgname) +\
                    'step%d_globaltag = %s\n' % (task, refsubgtshort) +\
                    'step%d_input = Task1\n\n' % (task)
                task += 1
                continue

            elif recodqm:
                for ds in options.ds :
                    ds_name = ds[:1].replace("/","") + ds[1:].replace("/","_")
                    ds_name = ds_name.replace("-","_")
                    label = cfgname.lower().replace('.py', '')[0:5]
                    ReqLabel = details['reqtype']+label
                    wmcconf_text += '\n[%s_%s_%s]\n' % (details['reqtype'], label, ds_name) +\
                                    'input_name = %s\n' % (ds) +\
                                    'request_id=%s__ALCA_%s-%s_%s_%s\n' % (options.release,options.jira,datetime.datetime.now().strftime("%Y_%m_%d_%H_%M"),ds_name,ReqLabel) +\
                                    'keep_step%d = True\n' % (task) +\
                                    'time_event = 1\n' +\
                                    'size_memory = 8000\n' +\
                                    'step1_lumisperjob = 1\n' +\
                                    'processing_string = %s_%s_%s \n' % (processing_string, details['reqtype']+label, refsubgtshort) +\
                                    'cfg_path = %s\n' % (cfgname) +\
                                    'req_name = %s_%s_RelVal_%s\n' % (details['reqtype'], label, onerun) +\
                                    'globaltag = %s\n' % (refsubgtshort) +\
                                    'step%d_output = %s\n' % (task, 'FEVTDEBUGoutput' if options.cosmics else 'FEVTDEBUGHLToutput') +\
                                    'step%d_cfg = recodqm_%s.py\n' % (task, label) +\
                                    'step%d_lumisperjob = 1\n' % (task) +\
                                    'step%d_globaltag = %s \n' % (task, gtshort) +\
                                    'step%d_processstring = %s_%s_%s \n' % (task, processing_string, details['reqtype']+label, refsubgtshort) +\
                                    'step%d_input = Task1\n' % (task) +\
                                    'step%d_timeevent = 10\n' % (task)

                    if options.recoRelease:
                        wmcconf_text += 'step%d_release = %s \n' % (task, options.recoRelease)
                    wmcconf_text += 'harvest_cfg=step4_%s_HARVESTING.py\n\n' %(label)
            else:
                continue
        if base:
            wmcconf_text += '\n\n' +\
                            'step%d_output = RAWRECOoutput\n' % (task) +\
                            'step%d_cfg = %s\n' % (task, cfgname) +\
                            'step%d_globaltag = %s\n' % (task, subgtshort) +\
                            'step%d_input = Task1\n\n' % (task)

            task += 1
        elif recodqm:
            if "REFERENCE" in cfgname:
                continue
            for ds in options.ds :
                ds_name = ds[:1].replace("/","") + ds[1:].replace("/","_")
                ds_name = ds_name.replace("-","_")
                label = cfgname.lower().replace('.py', '')[0:5]
                ReqLabel = details['reqtype']+label
                wmcconf_text += '\n\n[%s_%s_%s]\n' %(details['reqtype'], label, ds_name) +\
                                'input_name = %s\n' % (ds) +\
                                'request_id=%s__ALCA_%s-%s_%s_%s\n' % (options.release,options.jira,datetime.datetime.now().strftime("%Y_%m_%d_%H_%M"),ds_name,ReqLabel) +\
                                'keep_step%d = True\n' % (task) +\
                                'time_event = 1\n' +\
                                'size_memory = 8000\n' +\
                                'step1_lumisperjob = 1\n' +\
                                'processing_string = %s_%s_%s \n' % (processing_string, details['reqtype']+label, subgtshort) +\
                                'cfg_path = %s\n' % (cfgname) +\
                                'req_name = %s_%s_RelVal_%s\n' % (details['reqtype'], label, onerun) +\
                                'globaltag = %s\n' % (subgtshort) +\
                                'step%d_output = %s\n' % (task, 'FEVTDEBUGoutput' if options.cosmics else 'FEVTDEBUGHLToutput') +\
                                'step%d_cfg = recodqm_%s.py\n' % (task, label) +\
                                'step%d_lumisperjob = 1\n' % (task) +\
                                'step%d_globaltag = %s \n' % (task, gtshort) +\
                                'step%d_processstring = %s_%s_%s \n' % (task, processing_string, details['reqtype']+label, subgtshort) +\
                                'step%d_input = Task1\n' % (task) +\
                                'step%d_timeevent = 10\n' % (task)
                if options.recoRelease:
                    wmcconf_text += 'step%d_release = %s \n' % (task,options.recoRelease)
                wmcconf_text += 'harvest_cfg=step4_%s_HARVESTING.py\n\n' % (label)
        else:
            if(options.two_WFs == True):
                for ds in options.ds :
                    ds_name = ds[:1].replace("/","") + ds[1:].replace("/","_")
                    ds_name = ds_name.replace("-","_")
                    label = cfgname.lower().replace('.py', '')[0:5]
                    ReqLabel = details['reqtype']+label
                    wmcconf_text += '\n\n[%s_%s_%s]\n' % (details['reqtype'], label,ds_name) +\
                                    'input_name = %s\n' % (ds) +\
                                    'request_id=%s__ALCA_%s-%s_%s_%s\n' % (options.release,options.jira,datetime.datetime.now().strftime("%Y_%m_%d_%H_%M"),ds_name,ReqLabel) +\
                                    'keep_step1 = True\n' +\
                                    'time_event = 10\n' +\
                                    'size_memory = 8000\n' +\
                                    'step1_lumisperjob = 1\n' +\
                                    'processing_string = %s_%s_%s \n' % (processing_string, details['reqtype']+label, gtshort) +\
                                    'cfg_path = %s\n' % (cfgname) +\
                                    'req_name = %s_%s_RelVal_%s\n' % (details['reqtype'], label, onerun) +\
                                    'globaltag = %s\n' % (gtshort) +\
                                    'harvest_cfg=step4_%s_HARVESTING.py\n\n' % (label)
                ##END of FOR loop
            else:
                continue

    # compose string representing runs, Which will be part of the filename
    # if run is int => single label; if run||runLs are list or dict, '_'-separated composite label
    run_label_for_fn = ''

    if options.run and isinstance(options.run, int):
        run_label_for_fn = options.run
    elif options.run and isinstance(options.run, list):
        for oneRun in options.run:
            if run_label_for_fn != '':
                run_label_for_fn += '_'
            run_label_for_fn += str(oneRun)

    elif options.runLs and isinstance(options.runLs, dict):
        for oneRun in options.runLs:
            if run_label_for_fn != '':
                run_label_for_fn += '_'
            run_label_for_fn += str(oneRun)

    wmconf_name = '%sConditionValidation_%s_%s_%s.conf' % (details['reqtype'],
            options.release, gtshort, run_label_for_fn) # FOLLOW NAMING CONVENTION OF FILE FROM relval_submit.py

    if not DRYRUN:
        wmcconf = open(wmconf_name,'w')
        wmcconf.write(wmcconf_text)
        wmcconf.close()

    execme('./wmcontrol.py --test --req_file %s' % (wmconf_name))
    print('Now execute:\n./wmcontrol.py --req_file %s  |& tee wmcontrol.1.log' % (wmconf_name))

def printInfo(options):
    if "HLT" in options.Type or "EXPR+RECO" in options.Type:
        if options.HLT is not None:
            hltFilename = '%s/src/HLTrigger/Configuration/python/HLT_%s_cff.py' % (options.hltCmsswDir,
                    options.HLT)
        else:
            hltFilename = '%s/src/HLTrigger/Configuration/python/HLT_GRun_cff.py' % (options.hltCmsswDir)

        menu = None
        if os.path.exists(hltFilename):
            f = open(hltFilename)
            menu = f.readline()
            menu = menu.strip().split(":")[-1].strip()

    matched = re.match("(.*),(.*),(.*)", options.newgt)
    if matched:
        newgtshort = matched.group(1)
    else:
        newgtshort = options.newgt

    matched = re.match("(.*),(.*),(.*)", options.gt)
    if matched:
        gtshort = matched.group(1)
    else:
        gtshort = options.gt

    print("")
    print("type: %s" % (options.Type))
    print("dataset: %s" % (",".join(options.ds)))
    #print "run: %s" % (",".join(options.run))
    if (options.run):
        print("run: %s" % (",".join(options.run)))
    elif (options.runLs):
        print("run: %s" % (options.runLs))

    if "HLT" in options.Type or "EXPR+RECO" in options.Type:
        print("HLT menu: %s" % (menu))
        print("Target HLT GT: %s" % (newgtshort))
        print("Reference HLT GT: %s" % (gtshort))
    if "HLT" in options.Type and "RECO" in options.Type:
        print("Common Prompt GT: %s" % (options.basegt))
    if options.Type in ["PR", "EXPR"]:
        print("Target %s GT: %s" % (options.Type, newgtshort))
        print("Reference %s GT: %s" % (options.Type, gtshort))

#-------------------------------------------------------------------------------

if __name__ == "__main__":
    #Raise an error if couchID files exist
    import subprocess
    p = subprocess.Popen("ls", stdout=subprocess.PIPE, shell=True)
    out = p.stdout.read().strip()
    newlist = out.decode('utf-8').split('\n')
    substring = ".couchID"

    for object in newlist:
        if substring in object:
            raise ValueError("couchID file exists, please remove it")

    # Get the options
    options = createOptionParser()
    # this type is LIST in the normal CASE,
    # and it's also list with a single element == dictionary in the LS-filtering case. This is a problem


    # Check if it is at FNAL
    allRunsAndBlocks = {}
    if not options.noSiteCheck:
        for ds in options.ds:
            allRunsAndBlocks[ds] = []
            #  if run is ls-filtering, run numbers will be in lumi_list and must not be there
            if isinstance(options.run, dict): # if run is ls-filtering, run numbers will be in lumi_list and must not be there
                continue
            if not options.run:               # if run is not specified in the input file, leave allRunsAndBlocks empty
                continue

            for run in options.run:
                newblocks = isAtSite(ds, int(run))
                if newblocks == False:
                    print("Cannot proceed with %s in %s (no suitable blocks found)" % (ds, run))
                    sys.exit(1)
                else:
                    allRunsAndBlocks[ds].extend(newblocks)

    #uniquing
    for ds in allRunsAndBlocks:
        allRunsAndBlocks[ds] = list(set(allRunsAndBlocks[ds]))

    # Read the group of conditions from the list in the file
    confCondList = getConfCondDictionary(options)

    # Start
    collect_commands(options)
    # Create the cff
    if options.HLT in ["SameAsRun", "Custom"]: createHLTConfig(options)

    # Get list of input files
    step1(options)

    # Create the cfgs, both for cmsRun and WMControl
    createCMSSWConfigs(options, confCondList, allRunsAndBlocks)

    # Print some info about final workflow
    printInfo(options)
