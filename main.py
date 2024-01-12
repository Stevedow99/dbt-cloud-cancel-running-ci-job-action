import os
import subprocess
import requests
import time

# ------------------------------------------------------------------------------
# getting all of my inputs for use in the action
# ------------------------------------------------------------------------------

# setting the dbt cloud token to use dbt cloud API
dbt_cloud_token = os.environ["INPUT_DBT_CLOUD_TOKEN"]

# setting the dbt cloud account id
dbt_cloud_account_id = os.environ["INPUT_DBT_CLOUD_ACCOUNT_ID"]

# setting the dbt cloud job id
dbt_cloud_job_id = os.environ["INPUT_DBT_CLOUD_JOB_ID"]

# setting the dbt_cloud_host env, by default uses the standard url
dbt_cloud_host = os.environ.get('INPUT_DBT_CLOUD_HOST', 'cloud.getdbt.com')

# getting the flag only_cancel_run_if_commit_is_using_pr_branch 
# one note on this is in YAML it's passed as a bool aka true and in python it comes in as a string
same_branch_flag = os.environ.get('INPUT_ONLY_CANCEL_RUN_IF_COMMIT_IS_USING_PR_BRANCH', 'false')

# getting the maximum number of recent jobs
max_runs = os.environ.get('INPUT_MAX_RUNS', '10')

# getting the number of the github branch the PR is on - used only if only_cancel_run_if_commit_is_using_pr_branch is set to True
pr_branch_number = os.environ.get("INPUT_GITHUB_PR_NUMBER", 'none')

# getting the flag only_cancel_queued_starting_run
# one note on this is in YAML it's passed as a bool aka true and in python it comes in as a string
only_queued_starting = os.environ.get("INPUT_ONLY_CANCEL_QUEUED_STARTING_RUN", 'false')

# getting the flag cancel_runs_based_on_schema_override
use_schema_override_flag = os.environ.get("INPUT_CANCEL_RUNS_BASED_ON_SCHEMA_OVERRIDE", 'false')

# ------------------------------------------------------------------------------
# use environment variables to set dbt cloud api configuration
# ------------------------------------------------------------------------------

# setting the headers for the dbt cloud api request
req_auth_headers = {'Authorization': f'Token {dbt_cloud_token}'}

# setting the url for the dbt cloud api request
base_dbt_cloud_api_url = f'https://{dbt_cloud_host}/api/v2/accounts/{dbt_cloud_account_id}'

# setting the dbt cloud run status to human readable codes
# dbt run statuses are encoded as integers. This map provides a human-readable status
run_status_map = {
  1:  'Queued',
  2:  'Starting',
  3:  'Running',
  10: 'Success',
  20: 'Error',
  30: 'Cancelled',
}

# -------------------------------------------------------------------------------------------------------
# creating a function that takes the recent runs and filters them down depending on the same branch flag
# -------------------------------------------------------------------------------------------------------

def extract_dbt_runs_info(recent_runs_list, job_id, same_branch_flag, use_schema_override_flag):
    
    # setting an empty list to populate with run_ids and statuses
    recent_runs_info = []
    
    # looping thru the recent runs info and pulling out each jobs if and status
    for run in recent_runs_list:

        # getting run id
        run_id = run["id"]

        # getting run status
        run_status = run_status_map[run["status"]]

        # getting run url 
        run_url = run["href"]

        # checking if the same branch flag is set to true
        if same_branch_flag == "true":

            if use_schema_override_flag == "true":

                # grabbing the schema override to parse PR number when CI is triggered by external process
                run_schema_override = run['trigger']['schema_override']
                schema_override_prefix = f'dbt_cloud_pr_{str(job_id)}_'
                run_git_pr_number = None if run_schema_override is None else run_schema_override.lstrip(schema_override_prefix)
                # defaulting to not canceling the job if run_git_pr_number isn't an integer
                run_git_pr_number = None if run_git_pr_number is None or not run_git_pr_number.isnumeric() else int(run_git_pr_number)
            
            else:

                # grabbing the pr number from the dbt Cloud job run
                run_git_pr_number = run['trigger']['github_pull_request_id']

            # making sure the pr number isn't none before comparing to pr_branch_number
            if run_git_pr_number != None:

                # if the PR branch number matches the PR branch number of the branch that the job was run on - we put it into the runs list
                if run_git_pr_number == int(pr_branch_number):

                    # appending the elements to the list
                    recent_runs_info.append({"run_id" : run_id, "run_status" : run_status, "run_url" : run_url, "run_github_pr_number" : run_git_pr_number })

        # else if the same branch flag is not set to true
        else:
            
            # we add recent runs to the list regardless of branch name
            recent_runs_info.append({"run_id" : run_id, "run_status" : run_status, "run_url" : run_url})
    
    # returning the list of run info 
    return recent_runs_info

# ------------------------------------------------------------------------------
# setting a function to return the most recent runs for a given job
# ------------------------------------------------------------------------------

def get_recent_runs_for_job(base_url, headers, job_id, same_branch_flag, max_runs, use_schema_override_flag):

    # setting the request url
    dbt_cloud_runs_url = f'{base_url}/runs/?job_definition_id={job_id}&order_by=-id&include_related=["trigger"]&limit={max_runs}'

    # getting the last four runs excluding the most recent one as that is the current qued job
    # this assumes the job being triggered is the most recent job
    recent_runs = requests.get(dbt_cloud_runs_url, headers=headers, timeout=30).json()
    
    # using the function extract the recent runs
    recent_runs_info = extract_dbt_runs_info(recent_runs['data'], job_id, same_branch_flag, use_schema_override_flag)

    return recent_runs_info

# ------------------------------------------------------------------------------
# setting a function to cancel a CI job run if it's running
# ------------------------------------------------------------------------------

def cancel_dbt_cloud_job(base_url, headers, run_id): 

    # setting the request url
    dbt_cloud_run_cancel = f"{base_url}/runs/{run_id}/cancel"

    # get status of cancelled job
    cancelled_dbt_cloud_run = requests.post(dbt_cloud_run_cancel, headers=headers, timeout=30).json()

    # get run cancelled time, dbt api returns ["data"] ["data"] that's why we have an extra ["data"] 
    # need to hash this out with the API on why this is happening. For now, the try except works
    try:
        run_cancelled_timestamp = cancelled_dbt_cloud_run["data"]["finished_at"][:19]
    except:
        run_cancelled_timestamp = cancelled_dbt_cloud_run["data"]["data"]["finished_at"][:19]

    # returning the info on the cancelled runs
    return run_cancelled_timestamp

# ------------------------------------------------------------------------------
# running the main function
# ------------------------------------------------------------------------------

def main():

    # setting up an initial wait period just in case the job takes some time to kick off
    time.sleep(10)

    # getting the most recent runs of the given job
    most_recent_runs = get_recent_runs_for_job(base_url=base_dbt_cloud_api_url, headers=req_auth_headers, job_id=dbt_cloud_job_id, same_branch_flag=same_branch_flag, max_runs=max_runs, use_schema_override_flag=use_schema_override_flag)

    # creating a list to collect all cancelled runs
    cancelled_runs = []

    # looping the returned run, if there is some running or queued jobs, we cancel them in order to allow the most recent job to kick off
    for run in most_recent_runs:

        # if the run status is in an active state, we cancel accordingly to INPUT_ONLY_CANCEL_QUEUED_STARTING_RUN
        if only_queued_starting == "true":
            
            # cancel only queued and starting dbt runs
            to_cancel = ["Queued", "Starting"]
        
        else:
            
            # cancel queued, starting and running dbt runs
            to_cancel = ["Queued", "Starting", "Running"]

        if run["run_status"] in to_cancel:

            # cancelling the dbt run
            run_cancelled_timestamp = cancel_dbt_cloud_job(base_url=base_dbt_cloud_api_url, headers=req_auth_headers, run_id = run["run_id"])

            # putting info on the cancelled run in the list 
            cancelled_runs.append({"run_id" : run["run_id"], 
                                    "run_status" : run["run_status"], 
                                    "run_url" : run["run_url"],
                                    "run_cancelled_timestamp" : run_cancelled_timestamp })

    # if some runs were cancelled we script up some markdown to put in the PR comment and set the cancelled_jobs_flag to True
    if len(cancelled_runs) > 0:

        # setting the output of the cancelled_jobs_flag
        subprocess.call('echo "cancelled_jobs_flag={}" >> $GITHUB_OUTPUT'.format("True"), shell=True)

        # generating some markdown to use for PR comments
        pr_comment_markdown_code = "**The following dbt Cloud job runs were cancelled to free up the queue for the new CI job on the current PR:**"

        # setting a blank string for cancelled
        cancelled_runs_output = []

        # looping thru the cancelled runs and adding them to the markdown
        for run in cancelled_runs:

            # adding to the cancelled runs
            cancelled_runs_output.append(run['run_id'])

            # adding info on cancelled run
            pr_comment_markdown_code += f"<br>  - Run **{run['run_id']}** was cancelled at **{run['run_cancelled_timestamp']} UTC**, view this run in dbt Cloud [here]({run['run_url']})"

        # setting the output of the cancelled_dbt_cloud_job_runs
        subprocess.call('echo "cancelled_dbt_cloud_job_runs={}" >> $GITHUB_OUTPUT'.format(cancelled_runs_output), shell=True)

        # setting the output of the cancelled_dbt_cloud_job_markdown
        subprocess.call('echo "cancelled_dbt_cloud_job_runs_markdown={}" >> $GITHUB_OUTPUT'.format(pr_comment_markdown_code), shell=True)

    # else we set the cancelled_jobs_flag to False
    else:

         # setting the output of the cancelled_jobs_flag
        subprocess.call('echo "cancelled_jobs_flag={}" >> $GITHUB_OUTPUT'.format("False"), shell=True)

if __name__ == "__main__":
    main()