import os
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

# setting the job_check_interval
dbt_cloud_host = os.environ.get('INPUT_DBT_CLOUD_HOST', 'cloud.getdbt.com')

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

# ------------------------------------------------------------------------------
# setting a function to return the most recent runs for a given job
# ------------------------------------------------------------------------------

def get_recent_runs_for_job(base_url, headers, job_id):

    # setting the request url
    dbt_cloud_runs_url = f"{base_url}/runs/?job_definition_id={job_id}&order_by=-id"

    # getting the last four runs excluding the most recent one as that is the current qued job
    # this assumes the job being triggered is the most recent job
    recent_runs = requests.get(dbt_cloud_runs_url, headers=headers, timeout=30).json()['data'][1:6]
    
    # setting an empty list to populate with run_ids and statues
    recent_runs_info = []
    
    # looping thru the recent runs info and pulling out each jobs if and status
    for run in recent_runs:
    
        # getting run id
        run_id = run["id"]
        
        # getting run status
        run_status = run_status_map[run["status"]]
        
        # getting run url 
        run_url = run["href"]
        
        # appending the elements to the list
        recent_runs_info.append({"run_id" : run_id, "run_status" : run_status, "run_url" : run_url })

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

    # returning the run status
    return run_cancelled_timestamp

# ------------------------------------------------------------------------------
# running the main function
# ------------------------------------------------------------------------------

def main():
    # getting the most recent runs of the given job
    most_recent_runs = get_recent_runs_for_job(base_url=base_dbt_cloud_api_url, headers=req_auth_headers, job_id=dbt_cloud_job_id)

    # setting up an intial wait period just in case the job takes some time to kick off
    time.sleep(10)

    # creating a list to collect all cancelled runs
    cancelled_runs = []

    # looping the returned run, if there is some running or qued jobs, we cancel them in order to allow the most recent job to kick off
    for run in most_recent_runs:

        # if the run status is in an active state we cancel
        if run["run_status"] in ["Queued", "Starting", "Running"]:

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
        print(f"::set-output name=cancelled_jobs_flag::True")

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
        print(f"::set-output name=cancelled_dbt_cloud_job_runs::{cancelled_runs_output}")

        # setting the output of the cancelled_dbt_cloud_job_markdown
        print(f"::set-output name=cancelled_dbt_cloud_job_runs_markdown::{pr_comment_markdown_code}")

    # else we set the cancelled_jobs_flag to False
    else:

         # setting the output of the cancelled_jobs_flag
        print(f"::set-output name=cancelled_jobs_flag::False")

if __name__ == "__main__":
    main()