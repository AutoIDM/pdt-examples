# pdt-examples

Small scheduled jobs that IT teams actually run, ready to copy into your own [pdt](https://github.com/AutoIDM/pdt) project.

Most IT teams have a handful of scripts that someone runs by hand every week: a license report, an export before a change window, a check for accounts that should have been removed. They live on one person's laptop, and they stop when that person is on holiday. pdt runs those scripts on a schedule in your own cloud account (AWS, Azure, or Google Cloud) or in Windows Task Scheduler, keeps their output and logs, and keeps their passwords out of the code. You do not need to know containers or cloud services to use it; `pdt deploy` asks a few plain questions and does the rest.

Each folder here is one of those jobs. They are taken from real customer work, and they run against real systems on every change to pdt, so what you copy is known to work. Use one as it is, or as a starting point for your own.

## What is here

| Example | What it does | Written in | Runs |
| --- | --- | --- | --- |
| [`hello-world`](hello-world) | Writes one log line. A safe first job to try a deploy with. | Python | daily |
| [`azure-license-waste`](azure-license-waste) | Finds Microsoft 365 licenses you pay for that nobody uses (disabled accounts, people who have not signed in for 90 days, seats assigned to no one) and saves an Excel workbook with the monthly cost of each. | PowerShell | weekly |
| [`intune-export`](intune-export) | Backs up your Intune configuration with [IntuneManagement](https://github.com/Micke-K/IntuneManagement), keeps a dated zip of each export, and lists what changed since the last one. | PowerShell | weekly |
| [`monday-orphaned-account-report`](monday-orphaned-account-report) | Emails a list of active monday.com users who no longer have an active Entra ID account. | Python | daily |
| [`salesforce-netsuite-customer-sync`](salesforce-netsuite-customer-sync) | Copies Salesforce accounts and contacts into NetSuite customers and contacts, so sales and finance see the same companies. | Python (Meltano) | hourly |
| [`salesforce-netsuite-quote-to-cash`](salesforce-netsuite-quote-to-cash) | Turns a Closed Won Salesforce opportunity into a NetSuite sales order and invoice. Not finished yet, so pdt leaves it out. | Python (Meltano) | every 5 minutes |

Every example's `config.yml` starts with a short description, and says which permissions the job needs and which settings you can change. The two Salesforce examples also have their own `README.md`.

## Try one

If you do not have pdt yet, the [pdt README](https://github.com/AutoIDM/pdt#install) shows how to install it. It takes two commands, or one on Windows.

Then make a project of your own and copy an example into it. This uses `azure-license-waste`; any folder name from the table works the same way.

```
git clone https://github.com/AutoIDM/pdt-examples
pdt init my-jobs
cp -r pdt-examples/azure-license-waste my-jobs/
cd my-jobs
```

On Windows, use `Copy-Item -Recurse pdt-examples\azure-license-waste my-jobs\` in place of the `cp` line.

Next, give the job the passwords and keys it needs. If the example has an `env.template`, copy the names from it into a file called `.env` in `my-jobs` and fill in the values; otherwise the `env:` list in its `config.yml` names them. `.env` stays on your computer and is never committed. Check that nothing is missing, and run the job once on your own computer:

```
pdt validate
pdt run azure-license-waste
```

When you are happy with what it does, put it on its schedule:

```
pdt deploy azure-license-waste
```

The deploy shows you everything it will create and what it should cost each month before it changes anything, and asks before it goes ahead. `pdt destroy azure-license-waste` removes all of it again.

Please do not run the jobs from inside this folder. Its `pdt.yml` belongs to the account we test against, not to yours.

## Questions and ideas

If an example does not work for you, or you have a job in mind that you think would be useful here, please open an issue. We are glad to hear what other IT teams need.

## For pdt maintainers

This repository also tests pdt. The purpose is to make sure pdt works for real scenarios against real systems; it does not try to cover every environment. `pdt/verify` holds the comprehensive pdt tests.

- The examples must always work against pdt `master`.
- pdt CI fails when an example here breaks.
- CI here fails when an example does not work against pdt `master`. `.gitlab-ci.yml` builds pdt from the matching branch, or `master`, and runs every app that `pdt list --names` prints. An app with `enabled: false` in its `config.yml` is left out.

Still to do: test the docs in both repositories, so each documented command runs as a test.
