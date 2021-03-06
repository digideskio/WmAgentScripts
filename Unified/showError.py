#!/usr/bin/env python
from utils import workflowInfo, siteInfo, monitor_dir, base_dir, global_SI, getDatasetPresence
import json
import sys
import os
from collections import defaultdict
from assignSession import *
import time
import optparse

def parse_one(url, wfn, options=None):

    SI = global_SI()
    wfi = workflowInfo( url , wfn)
    where_to_run, missing_to_run,missing_to_run_at = wfi.getRecoveryInfo()       
    all_blocks,needed_blocks,files_in_blocks,files_notin_dbs = wfi.getRecoveryBlocks()

    ancestor = workflowInfo( url , wfn)
    lhe,prim,_,sec = ancestor.getIO()
    high_order_acdc = 0
    while ancestor.request['RequestType'] == 'Resubmission':
        ancestor = workflowInfo(url, ancestor.request['OriginalRequestName'])
        lhe,prim,_,sec = ancestor.getIO()
        high_order_acdc += 1

    no_input = (not lhe) and len(prim)==0 and len(sec)==0

    cache = 0
    if options:
        cache = options.cache
    print "cache timeout", cache

    err= wfi.getWMErrors(cache=cache)
    stat = wfi.getWMStats(cache=cache)
    #adcd = wfi.getRecoveryDoc()

    total_by_code_dash = defaultdict( int )
    total_by_site_dash = defaultdict( int )
    r_dashb =defaultdict( lambda : defaultdict( int ))
    dash_board_h = 1
    if True :#'pdmvserv_TOP-RunIISummer15wmLHEGS-00103_00183_v0__161005_165048_809' in wfn:
        ## NB get the since from when the wf has started, not a fixed value
        ## no dashboard until we get a better api
        #dashb = wfi.getFullPicture(since=dash_board_h,cache=cache)
        dashb = {}
        #print json.dumps( dashb , indent=2)
        for site,sinfo in dashb.items():
            for s_code,counts in sinfo.items():
                d_statuses = ['submitted','pending','app-unknown','done']
                total_by_code_dash[str(s_code)]+= counts.get('submitted',0)
                total_by_site_dash[site] += counts.get('submitted',0)
                r_dashb[str(s_code)][site] += counts.get('submitted',0)

        print json.dumps(total_by_code_dash , indent=2)
        print json.dumps(total_by_site_dash , indent=2)

    status_per_task = defaultdict(lambda : defaultdict(int))
    
    if not 'AgentJobInfo' in stat:
        stat['AgentJobInfo'] = {}
        #print "bad countent ?"
        #print json.dumps(  stat,  indent=2)

    for agent in stat['AgentJobInfo']:
        for task in stat['AgentJobInfo'][agent]['tasks']:
            if not 'status' in stat['AgentJobInfo'][agent]['tasks'][task]: continue
            for status in stat['AgentJobInfo'][agent]['tasks'][task]['status']:
                info = stat['AgentJobInfo'][agent]['tasks'][task]['status'][status]
                #print status,stat['AgentJobInfo'][agent]['tasks'][task]['status'][status]
                if type(info)==dict:
                    status_per_task[task][status] += sum( stat['AgentJobInfo'][agent]['tasks'][task]['status'][status].values())
                else:
                    status_per_task[task][status] += stat['AgentJobInfo'][agent]['tasks'][task]['status'][status]

    #print json.dumps( status_per_task, indent=2)
    db_total_per_site = defaultdict(int) 
    db_total_per_code = defaultdict(int)
    ## cannot do that since there is no task count in dashboard and we have to take away the submitted
    #for site in dashb:
    #    for error in dashb[site]:
    #        db_total_per_site[site] += dashb[site][error] 
    #        db_total_per_code[code] += dashb[site][error]
    
    print "ACDC Information"
    print json.dumps( where_to_run , indent=2)         
    print json.dumps(missing_to_run , indent=2)        
    print json.dumps(missing_to_run_at , indent=2)        
    
    task_error_site_count ={}
    one_explanation = defaultdict(set)

    do_JL = True
    do_CL = True
    do_all_error_code = False
    if options: 
        do_JL = not options.no_JL
        do_CL = not options.no_CL
        do_all_error_code = options.all_errors
    if high_order_acdc>=1:
        print high_order_acdc,"order request, pulling down all logs"
        do_all_error_code = True

    n_expose = 1
    if options:
        n_expose = options.expose 
    expose_archive_code = {'134':defaultdict(lambda : n_expose),#seg fault
                           '139':defaultdict(lambda : n_expose),# ???
                           '99109':defaultdict(lambda : n_expose),#stageout
                           '99303' : defaultdict(lambda : n_expose),#no pkl report. if you are lucky
                           '60450' : defaultdict(lambda : n_expose),#new
                           '50513':defaultdict(lambda : n_expose),#new
                           '8001': defaultdict(lambda : n_expose),# the usual exception in cmsRun
                           '11003': defaultdict(lambda : n_expose),# job extraction
                           '73': defaultdict(lambda : n_expose),# job extraction
                           }
    expose_condor_code = {'99109':defaultdict(lambda : n_expose),#stageout
                          '99303':defaultdict(lambda : n_expose),#no pkl report
                          '60450':defaultdict(lambda : n_expose),#new
                          '50513':defaultdict(lambda : n_expose),#new
                          '11003': defaultdict(lambda : n_expose),
                          }
    
    tasks = sorted(set(err.keys() + missing_to_run.keys()))

    if not tasks:
        print "no task to look at"
        #return task_error_site_count
        
    html="<html> <center><h1><a href=https://cmsweb.cern.ch/reqmgr2/fetch?rid=%s>%s</a><br><a href=https://dmytro.web.cern.ch/dmytro/cmsprodmon/workflows.php?prep_id=%s>%s</a><br>"%(
        wfn,
        wfn,
        wfi.request['PrepID'],
        wfi.request['PrepID']
        )
    if wfi.request['RequestType'] in ['ReReco']:
        html += '<a href=../datalumi/lumi.%s.html>Lumisection Summary</a><br>'% wfi.request['PrepID']
        
    html+= '</center><hr>'
    if prim:
        html+='Reads in primary<br>'
        for dataset in prim:
            presence = getDatasetPresence(url, dataset)
            html +='<b>%s</b><ul>'%dataset
            for site in sorted(presence.keys()):
                html += '<li>%s : %.2f %%'%( site, presence[site][1] )
            html+='</ul><br>'
    if sec:
        html+='Reads in secondary<br>'
        for dataset in sec:
            presence = getDatasetPresence(url, dataset)
            html +='<b>%s</b><ul>'%dataset
            for site in sorted(presence.keys()):
                html += '<li>%s : %.2f %%'%( site, presence[site][1] )
            html+='</ul>'
        
    html += "Updated on %s (GMT)" % ( time.asctime(time.gmtime()) )
    html += """
<ul>
<li> <b><i>dashboard numbers over %d days</b></i>
<li> &uarr; %% with respect to total number of error in the code
<li> &rarr; %% with respect to total number of error at the site
</ul>
"""%(dash_board_h)

    html += '<hr><br>'

    if tasks:
        min_rank = min([task.count('/') for task in tasks])
    for task in tasks:  
        #print task
        task_rank = task.count('/')
        task_short = task.split('/')[-1]
        total_per_site = defaultdict(int)
        for agent in stat['AgentJobInfo']:
            if not task in stat['AgentJobInfo'][agent]['tasks']: continue
            if not 'sites' in stat['AgentJobInfo'][agent]['tasks'][task]:continue
            for site in stat['AgentJobInfo'][agent]['tasks'][task]['sites']:

                info = stat['AgentJobInfo'][agent]['tasks'][task]['sites'][site]
                #if site in ['T2_BE_IIHE']:                    print task,json.dumps( info, indent=2)
                #print info.keys()
                for s in ['success','failure','cooloff','submitted']:
                    if not s in info: continue
                    data = info[s]
                    #print s,data
                    if type(data)==dict:
                        total_per_site[site] += sum( data.values() )
                    else:
                        total_per_site[site] += data

        #is the task relevant to recover (discard log, cleanup)
        if any([v in task.lower() for v in ['logcol','cleanup']]): continue


        total_count= defaultdict(int)
        error_site_count = defaultdict( lambda : defaultdict(int))
        if not task in err:
            print task,"has not reported error"
            err[task] = {}
        #print err[task].keys()
        
        for exittype in err[task]:
            #print "\t",err[task][exittype].keys()
            for errorcode_s in err[task][exittype]:
                if errorcode_s == '0' : continue
                #print "\t\t",err[task][exittype][errorcode_s].keys()
                for site in err[task][exittype][errorcode_s]:
                    ce = SI.SE_to_CE(site)
                    count = err[task][exittype][errorcode_s][site]['errorCount']
                    total_count[errorcode_s] += count
                    #error_site_count[errorcode_s][site] += count
                    error_site_count[errorcode_s][ce] += count
                    for sample in err[task][exittype][errorcode_s][site]['samples']:
                        #print sample.keys()
                        for step in sample['errors']:
                            for report in  sample['errors'][step]:
                                if report['type'] == 'CMSExeption': continue
                                #if int(report['exitCode']) == int(errorcode_s):
                                one_explanation[errorcode_s].add("%s (Exit code: %s) \n%s"%(report['type'], report['exitCode'], report['details']))
                                #one_explanation[errorcode_s].add( report['details'] )
                                #else:
                                #one_explanation[
                        agent = sample['agent_name']
                        wmbs = sample['wmbsid']
                        workflow = sample['workflow']

                        if do_CL and ((errorcode_s in expose_condor_code and expose_condor_code[errorcode_s][agent]) or do_all_error_code) and 'cern' in agent:
                            os.system('ssh %s %s/WmAgentScripts/Unified/exec_expose.sh %s %s %s %s %s %s'%( agent, base_dir, workflow, wmbs, errorcode_s, base_dir, monitor_dir, task_short))
                            if errorcode_s in expose_condor_code:
                                expose_condor_code[errorcode_s][agent]-=1

                        for out in sample['output']:
                            #print out
                            if out['type'] == 'logArchive':
                                if do_JL and ((errorcode_s in expose_archive_code and expose_archive_code[errorcode_s][agent]) or (do_all_error_code)):
                                    if errorcode_s in expose_archive_code:
                                        expose_archive_code[errorcode_s][agent]-=1
                                    os.system('mkdir -p /tmp/%s'%(os.getenv('USER')))
                                    local = '/tmp/%s/%s'%(os.getenv('USER'),out['lfn'].split('/')[-1])
                                    command = 'xrdcp root://cms-xrd-global.cern.ch/%s %s'%( out['lfn'], local)
                                    ## get the file
                                    os.system( command )
                                    ## if this actually fail, let's get the file from eos using the new log mapping
                                    ## expose the content
                                    label=out['lfn'].split('/')[-1].split('.')[0]
                                    m_dir = '%s/joblogs/%s/%s/%s/%s'%(monitor_dir, 
                                                                   wfn, 
                                                                   errorcode_s,
                                                                   task_short,
                                                                   label)
                                    os.system('mkdir -p %s'%(m_dir))
                                    os.system('tar zxvf %s -C %s'%(local,m_dir))
                                    ## truncate the content ??
                                    for fn in os.popen('find %s -type f'%(m_dir)).read().split('\n'):
                                        if not fn: continue
                                        if any([p in fn for p in ['stdout.log']]):
                                            trunc = '/tmp/%s/%s'%(os.getenv('USER'), label)
                                            #print fn
                                            #print trunc
                                            head = tail = 1000
                                            os.system('(head -%d ; echo;echo;echo "<snip>";echo;echo ; tail -%d ) < %s > %s'%(head, tail, fn, trunc))
                                            os.system('mv %s %s'%(trunc, fn))

        #print task
        #print json.dumps( total_count, indent=2)
        #print json.dumps( explanations , indent=2)
        all_sites = set()
        all_codes = set()
        for code in error_site_count:
            for site in error_site_count[code]:
                all_sites.add( site )
                if code != '0':
                    all_codes.add( code)

        ## parse the dashboard data
        for site in total_by_site_dash:
            ## no. cannot discriminate by task in dashboard...
            #all_sites.add( site )
            pass

        ## parse the acdc data
        notreported='NotReported'
        all_missing_stats = set()
        for site in missing_to_run_at[task]:
            if not missing_to_run_at[task][site]: continue
            ce = SI.SE_to_CE( site )
            #all_sites.add( ce )
            all_missing_stats.add( ce )

            error_site_count[notreported][ce] = 0
            all_codes.add(notreported)
            ## no error code at that point
            
        all_missing_stats = all_missing_stats &set(SI.all_sites)
        all_not_reported = all_missing_stats - all_sites 
        #print task
        #print "site with no report",sorted(all_not_reported)
        #print sorted(all_sites)
        #print sorted(all_missing_stats)
        all_sites = all_missing_stats | all_sites
        all_sites = all_sites & set(SI.all_sites)
        #success = total_count['0']
        #total_jobs = sum(total_count.values())
        #print total_jobs,"jobs in total,",success,"successes"
        #miss = "{:,}".format(missing_to_run[task]) if task in missing_to_run else "N/A"

        ## show the total
        s_per_code =defaultdict(int)
        for site in all_sites:
            for code in sorted(all_codes):
                s_per_code[code] += error_site_count[code][site]

        #no_error = (sum(s_per_code.values())==0)
        no_error = len(all_not_reported)!=0

        if not no_error and notreported in all_codes:
            all_codes.remove( notreported )
        missing_events = missing_to_run[task] if task in missing_to_run else 0
        html += "<b>%s</b>"%task.split('/')[-1]
        if missing_events:
            html += " is missing <b>%s events</b>"%( "{:,}".format(missing_events) )
            if no_error:
                html +="<br><b><font color=red> and has UNreported error</font></b>"


        html += "<br><table border=1><thead><tr><th>Sites/Errors</th>"

        #for site in all_sites:
        #    html+='<th>%s</th>'%site
        for code in sorted(all_codes):
            html+='<th><a href="#%s">%s</a>'%(code,code)
            if str(code) in expose_archive_code or do_all_error_code:
                html += ' <a href=../joblogs/%s/%s/%s>, JL</a>'%( wfn, code, task_short )
            if str(code) in expose_condor_code or do_all_error_code:
                html += ' <a href=../condorlogs/%s/%s/%s>, CL</a>'%( wfn, code, task_short )
            html += '</th>'

        html+='<th>Total jobs</th><th>Site Ready</th>'
        html+='</tr></thead>\n'

        html+='<tr><td>Total</td>'
        for code in sorted(all_codes):
            html += '<td bgcolor=orange width=100>%d'%(s_per_code[code])
            if code in total_by_code_dash:
                html += ' (<b><i>%d</i></b>)'% total_by_code_dash[code]
            html += '</td>'

        ulist='<ul>'
        grand=0
        for status in sorted(status_per_task[task].keys()):
            ulist+='<li> %s %d'%( status, status_per_task[task][status])
            grand+= status_per_task[task][status]
        ulist+='<li><b> Total %d </b>'%grand
        ulist+='</ul>'
        #html += '<td bgcolor=orange> %.2f%% </td>'% (100.*(float(sum(s_per_code.values()))/sum(total_per_site.values())) if sum(total_per_site.values()) else 0.)
        html += '<td bgcolor=orange> &rarr; %.2f%% &larr; </td>'% (100.*(float(sum(s_per_code.values()))/ grand) if grand else 0.)
        html += '<td bgcolor=orange> %s </td>'% ulist
        
        html+='</tr>'


        def palette(frac):
            _range = { 
                0.0 : 'green',
                0.5 : 'green',
                0.6 : 'darkgreen',
                0.7 : 'orange',
                0.8 : 'salmon',
                0.9 : 'red'
                }
            which = [k for k in _range.keys() if k<=frac]
            if which:
                there = max(which)
            else:
                there=max(_range.keys())
            return _range[there]

        for site in sorted(all_sites):
            site_in = 'Yes'
            color = 'bgcolor=lightblue'
            if not site in SI.sites_ready:
                color = 'bgcolor=indianred'
                site_in ='<b>No</b>'
                if missing_to_run_at[task][SI.CE_to_SE(site)] == 0 or min_rank == task_rank:
                    color = 'bgcolor=aquamarine'
                    site_in = '<b>No</b> but fine'

            if not no_error:
                site_in +=" (%s events)"%"{:,}".format(missing_to_run_at[task][SI.CE_to_SE(site)])
            html+='<tr><td %s>%s</td>'%(color,site)
            for code in sorted(all_codes):
                if code == notreported:
                    html += '<td %s width=200>%s events </td>' %(color, "{:,}".format(missing_to_run_at[task][SI.CE_to_SE(site)]))
                else:
                    if error_site_count[code][site]:
                        er_frac = float(error_site_count[code][site])/s_per_code[code] if s_per_code[code] else 0.
                        si_frac = float(error_site_count[code][site])/total_per_site[site] if total_per_site[site] else 0.
                        html += '<td %s width=200>%d'%(color, error_site_count[code][site])
                        if code in r_dashb and site in r_dashb[code]:
                            html += ' (<b><i>%d</i></b>)'%( r_dashb[code][site] )

                        html += ', <font color=%s>&uarr; %.1f%%</font>, <font color=%s>&rarr; %.1f%%</font></td>'% (
                            palette(er_frac),100.*er_frac,
                            palette(si_frac), 100.*si_frac
                            )
                    else:
                        html += '<td %s>0</td>'% color
            html += '<td bgcolor=orange>%d</td>'% total_per_site[site]
            html += '<td %s>%s</td>'% (color, site_in)
            html +='</tr>\n'
        html+='</table><br>'
        task_error_site_count[task] = error_site_count

    html += '<hr><br>'
    html += "<b>Blocks (%d/%d) needed for recovery</b><br>"%( len(needed_blocks), len(all_blocks))
    for block in sorted(needed_blocks):
        html +='%s<br>'%block
    html += "<br><b>Files in no block</b><br>"
    for f in sorted(files_notin_dbs):
        html +='%s<br>'%f


    html += '<hr><br>'
    html += '<table border=1>'
    for code in one_explanation:
        html +='<tr><td><a name="%s">%s</a></td><td>%s</td></tr>'% ( code, code, '<br><br>'.join(one_explanation[code]).replace('\n','<br>' ))
        #explanations[code].update( one_explanation[code] )
    html+='</table>'
    html+=('<br>'*30)
    html +='</html>'
    wfi.sendLog( 'error', html, show=False)
    fn = '%s'% wfn
    open('%s/report/%s'%(monitor_dir,fn),'w').write( html )

    return task_error_site_count, one_explanation

def parse_all(url, options=None):
    explanations = defaultdict(set)
    alls={}
    for wfo in session.query(Workflow).filter(Workflow.status == 'assistance-manual').all():    
        task_error, one_explanation = parse_one( url, wfo.name, options)
        alls.update( task_error )
        for code in one_explanation:
            explanations[code].update( one_explanation[code] )

    open('%s/all_errors.json'%monitor_dir,'w').write( json.dumps(alls , indent=2 ))

    explanations = dict([(k,list(v)) for k,v in explanations.items()])

    open('%s/explanations.json'%monitor_dir,'w').write( json.dumps(explanations, indent=2))

    alls = json.loads( open('all_errors.json').read())

    affected=set()
    per_code = defaultdict(set)
    for task in alls:
        for code in alls[task]:
            per_code[code].add( task.split('/')[1])
        
    for code in per_code:
        print code
        print json.dumps( sorted(per_code[code]), indent=2)


if __name__=="__main__":
    url = 'cmsweb.cern.ch'

    parser = optparse.OptionParser()
    parser.add_option('--no_JL',help="Do not get the job logs", action="store_true",default=False)
    parser.add_option('--no_CL',help="Do not get the condor logs", action="store_true",default=False)
    parser.add_option('--fast',help="Retrieve from cache and no logs retrieval", action="store_true", default=False)
    parser.add_option('--cache',help="The age in second of the error report before reloading them", default=0, type=float)
    parser.add_option('--workflow','-w',help="The workflow to make the error report of",default=None)
    parser.add_option('--expose',help="Number of logs to retrieve",default=1,type=int)
    parser.add_option('--all_errors',help="Bypass and expose all error codes", default=False, action='store_true')
    (options,args) = parser.parse_args()
    
    if options.fast:
        options.cache = 1000000
        options.no_JL = True
        options.no_CL = True

    if options.workflow:
        parse_one(url, options.workflow, options)
    else:
        parse_all(url, options)
