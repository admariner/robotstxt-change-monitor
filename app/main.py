#!/usr/bin/env python3
""" Monitor changes across one or more robots.txt files.
https://github.com/Cmastris/robotstxt-change-monitor
"""

import csv
import difflib
import os
import time

import requests

import config
import emails
import logs


def sites_from_file(file):
    """Extract monitored sites data from a CSV and return as a list of lists.

    Args:
        file (str): file location of a CSV file with the following attributes:
            - Header row labelling the three columns, as listed below.
            - url (col1): the absolute URL of the website homepage, with a trailing slash.
            - name (col2): the website's name identifier (letters/numbers only).
            - email (col3): the email address of the site admin if emails are enabled.
                            Note: an email header row label is required but email addresses
                            don't need to be populated if emails are disabled.

    """
    data = []
    with open(file, 'r') as sites_file:
        csv_reader = csv.reader(sites_file, delimiter=',')
        row_num = 0
        for row in csv_reader:
            # Skip the header row labels
            if row_num > 0:
                try:
                    data.append([row[0], row[1], row[2]])
                except Exception as e:
                    err_msg = logs.get_err_str(e, "Couldn't extract row {} from CSV."
                                               "".format(row_num))
                    logs.log_error(err_msg)

            row_num += 1

    return data


class RunChecks:
    """Run robots.txt checks across monitored websites.

    This class is used to run robots.txt checks by initialising RobotsCheck instances,
    before initialising the relevant Report subclass to generate logs and communications.

    Attributes:
        sites (list): a list of lists, with each list item representing a single site's
        attributes in the form [url, name, email]. Each attribute is detailed below.
            - url (str): the absolute URL of the website homepage, with a trailing slash.
            - name (str): the website's name identifier (letters/numbers only).
            - email (str): the email address of the site admin if emails are enabled,
                           otherwise an empty string.

        no_change (int): a count of site checks with no robots.txt change.
        change (int): a count of site checks with a robots.txt change.
        first_run (int): a count of site checks which were the first successful check.
        error (int): a count of site checks which could not be completed due to an error.

    """

    def __init__(self, sites):
        self.sites = sites.copy()
        self.no_change, self.change, self.first_run, self.error = 0, 0, 0, 0

        # If /data doesn't exist yet, create directory and main log file
        if not os.path.isdir(config.PATH + 'data'):
            os.mkdir(config.PATH + 'data')
            f = open(config.MAIN_LOG, 'x')
            f.close()

    def check_all(self):
        """Run robots.txt checks and reports for all sites."""
        start_content = "Starting checks on {} sites.".format(len(self.sites))
        logs.update_main_log(start_content)
        print(start_content)

        self.reset_counts()
        for site_attributes in self.sites:
            self.check_site(site_attributes)

        summary = "Checks and reports complete. No change: {}. Change: {}. First run: {}. " \
                  "Error: {}.".format(self.no_change, self.change, self.first_run, self.error)

        print("\n" + summary)
        logs.update_main_log(summary, blank_before=True)
        emails.send_emails(emails.site_emails)

        email_subject = "Robots.txt Checks Complete"
        email_body = emails.get_admin_email_body(summary)
        emails.admin_email.append((config.ADMIN_EMAIL, email_subject, email_body, config.MAIN_LOG))

    def check_site(self, site_attributes):
        """Run a robots.txt check and report for a single site.

        Attributes:
            site_attributes (list): a list representing a single site's attributes
            in the form [url, name, email]. Each attribute is detailed below.
                - url (str): the absolute URL of the website homepage, with a trailing slash.
                - name (str): the website's name identifier (letters/numbers only).
                - email (str): the email address of the site admin, who will receive alerts.

        """
        try:
            url, name, email = site_attributes
            url = url.strip().lower()
            email = email.strip()

            check = RobotsCheck(url)
            check.run_check()

            if check.err_message:
                report = ErrorReport(check, name, email)
                self.error += 1
            elif check.first_run:
                report = FirstRunReport(check, name, email)
                self.first_run += 1
            elif check.file_change:
                report = ChangeReport(check, name, email)
                self.change += 1
            else:
                report = NoChangeReport(check, name, email)
                self.no_change += 1

            report.create_reports()

        # Prevent all site checks failing; log error to investigate
        except Exception as e:
            err_msg = logs.get_err_str(e, "Unexpected error for site: {}.".format(site_attributes))
            logs.log_error(err_msg)

            email_subject = "Robots.txt Check Error"
            email_content = "There was an unexpected error while checking or reporting on the " \
                            "robots.txt file of a site which is associated with your email. " \
                            "If this is the first check, please ensure all site details " \
                            "were provided in the correct format. The error details are " \
                            "shown below.\n\n{}".format(err_msg)

            email_content = emails.replace_angle_brackets(email_content)
            email_body = emails.get_site_email_body(email_content)
            emails.site_emails.append((site_attributes[2].strip(), email_subject, email_body))
            self.error += 1

    @logs.unexpected_exception_handling
    def reset_counts(self):
        """Reset all report type counts back to zero."""
        self.no_change, self.change, self.first_run, self.error = 0, 0, 0, 0


class RobotsCheck:
    """Check a website's robots.txt file and compare to the previous recorded file.

    This class is used to download the robots.txt file, update the robots.txt records
    (current file and file downloaded during the previous run), and check for
    any differences between the records. The results (change, no change, first run, err)
    are assigned as attributes and the instance is returned.

    Attributes:
        url (str): the absolute URL of the website homepage, with a trailing slash.
        first_run (bool): if this is the first recorded check of the website's file.
        err_message (None, str): None by default, otherwise a description of the error.
        file_change (bool): if the robots.txt file has changed since the previous record.
        dir (str): the location of the directory containing website data.
        old_file (str): the file location of the previous check robots.txt content.
        new_file (str): the file location of the latest check robots.txt content.
        old_content (str): the previous check robots.txt content (assigned in 'update_records()').
        new_content (str): the latest check robots.txt content (assigned in 'update_records()').

    """

    def __init__(self, url):
        self.url = url
        # Updated where appropriate as the check progresses
        self.first_run = False
        self.err_message = None
        self.file_change = False
        # Use site domain name as directory name
        if self.url[:5] == 'https':
            self.dir = config.PATH + "data/" + self.url[8:-1]
        else:
            self.dir = config.PATH + "data/" + self.url[7:-1]
        self.old_file = self.dir + "/program_files/old_file.txt"
        self.new_file = self.dir + "/program_files/new_file.txt"
        # Content assigned during 'update_records()' after a successful check
        self.old_content = None
        self.new_content = None

        if (self.url[:4] != "http") or (self.url[-1] != "/"):
            self.err_message = "{} is not a valid site URL. The site URL must be absolute and " \
                               "end in a slash, e.g. 'https://www.example.com/'.".format(url)

        # If URL is valid and site directory doesn't exist, create required directories
        elif not os.path.isdir(self.dir):
            try:
                os.mkdir(self.dir)
                os.mkdir(self.dir + "/program_files")

            except Exception as e:
                self.err_message = logs.get_err_str(e, "Error creating {} directories."
                                                       "".format(self.url))
                logs.admin_email_errors.append(self.err_message)

    def __str__(self):
        return "RobotsCheck - {}".format(type(self).__name__, self.url)

    def run_check(self):
        """Update the robots.txt file records and check for changes.

        Returns:
            The class instance representing the completed robots.txt check.
        """
        if self.err_message:
            # If error/invalid URL during __init__
            return self

        try:
            extraction = self.download_robotstxt()
            self.update_records(extraction)
            if not self.first_run:
                self.check_diff()

        except Exception as e:
            # Anticipated errors caught in 'download_robotstxt()' and logged in 'self.err_message'
            if not self.err_message:
                self.err_message = logs.get_err_str(e, "Unexpected error during {} check."
                                                    "".format(self.url))

                logs.admin_email_errors.append(self.err_message)

        return self

    def download_robotstxt(self, max_attempts=5, wait=120):
        """Extract and return the current content (str) of the robots.txt file.

        Args:
            max_attempts (int): the maximum number of robots.txt URL connection attempts.
            wait (int): the number of seconds between connection attempts.

        """
        robots_url = self.url + "robots.txt"

        for attempt in range(max_attempts):
            attempts_str = " Trying again in {} seconds. " \
                           "Attempt {} of {}.".format(wait, attempt + 1, max_attempts)

            try:
                headers = {'User-Agent': config.USER_AGENT}
                req = requests.get(robots_url, headers=headers, allow_redirects=False, timeout=40)

            except requests.exceptions.Timeout as e:
                err = "{} timed out before sending a valid response.".format(robots_url)
                if attempt < (max_attempts - 1):
                    print(err + attempts_str)
                    time.sleep(wait)
                else:
                    # Final connection attempt failed
                    self.err_message = logs.get_err_str(e, err, trace=False)
                    raise

            except requests.exceptions.ConnectionError as e:
                err = "There was a connection error when accessing {}.".format(robots_url)
                if attempt < (max_attempts - 1):
                    print(err + attempts_str)
                    time.sleep(wait)
                else:
                    # Final connection attempt failed
                    self.err_message = logs.get_err_str(e, err)
                    logs.admin_email_errors.append(self.err_message)
                    raise

            else:
                # If no exceptions raised
                if req.status_code != 200:
                    self.err_message = "{} returned a {} status code." \
                                       "".format(robots_url, req.status_code)
                    raise requests.exceptions.HTTPError

                # URL was successfully reached and returned a 200 status code
                return req.text

    def update_records(self, new_extraction):
        """Update the files and attributes containing the current and previous robots.txt content.

        If the robots.txt file has been successfully checked previously, overwrite the contents
        of 'self.old_file' with the contents of 'self.new_file' (from the previous check).
        Otherwise, create the content files and set 'self.first_run' = True. Then, add the new
        robots.txt extraction content to 'self.new_file'. During this process, 'self.old_content'
        and 'self.new_content' are also updated by reading from the updated files.

        Args:
            new_extraction (str): the current content of the robots.txt file.

        """
        if os.path.isfile(self.new_file):
            # Overwrite the contents of old_file with the contents of new_file
            with open(self.old_file, 'w') as old, open(self.new_file, 'r') as new:
                self.old_content = new.read()
                old.write(self.old_content)

        else:
            # Create robots.txt content files if they don't exist (first non-error run)
            with open(self.old_file, 'x'), open(self.new_file, 'x'):
                pass

            self.first_run = True

        # Overwrite the contents of new_file with new_extraction
        # Characters which can't be encoded are replaced with an escape sequence
        with open(self.new_file, 'w', errors='backslashreplace') as new:
            new.write(new_extraction)

        # Read content from both files to avoid reading-related comparison inconsistencies
        with open(self.new_file, 'r') as new:
            self.new_content = new.read()

    def check_diff(self):
        """Check for robots.txt content differences and update 'self.file_change'."""
        if self.old_content != self.new_content:
            self.file_change = True


class Report:
    """Report the results of a single robots.txt check (base class; do not instantiate).

    Attributes:
        url (str): the absolute URL of the website homepage, with a trailing slash.
        dir (str): the name of the directory containing website data.
        new_content (str): the latest check robots.txt content.
        name (str): the website's name identifier (letters/numbers only).
        email (str): the email address of the site admin, who will receive alerts.
        timestamp (str): the approximate time of the check.

    """

    def __init__(self, website, name, email):
        self.url = website.url
        self.dir = website.dir
        self.new_content = website.new_content
        self.name = name
        self.email = email
        self.timestamp = logs.get_timestamp()

    def __str__(self):
        return "{} - {}".format(type(self).__name__, self.url)

    @logs.unexpected_exception_handling
    def update_site_log(self, message):
        """Update the site log text file with a single message (str)."""
        log_file = self.dir + "/log.txt"

        # Create file if it doesn't exist, otherwise append content to the end
        with open(log_file, 'a+') as f:
            f.write("{}: {}\n".format(self.timestamp, message))

    @logs.unexpected_exception_handling
    def create_snapshot(self):
        """Create and return the location of a text file containing the latest content."""
        file_name = self.timestamp.replace(",", " T").replace(":", "-") + " Robots.txt Snapshot.txt"
        snapshot_file = self.dir + "/snapshots/" + file_name
        if not os.path.isdir(self.dir + "/snapshots"):
            os.mkdir(self.dir + "/snapshots")

        with open(snapshot_file, 'x') as f:
            f.write(self.new_content)

        return snapshot_file


class NoChangeReport(Report):
    """Log and print the result (no robots.txt change) of a single robots.txt check."""

    def create_reports(self):
        """Update the site log and print result."""
        log_content = "No change: {}. No changes to robots.txt file.".format(self.url)
        self.update_site_log(log_content)
        print(log_content)


class ChangeReport(Report):
    """Log, print, and email the result (robots.txt change) of a single robots.txt check.

    Attributes:
        old_file (str): the file location of the previous check robots.txt content.
        new_file (str): the file location of the latest check robots.txt content.
        old_content (str): the previous check robots.txt content.

    """

    def __init__(self, website, name, email):
        super().__init__(website, name, email)
        self.old_file = website.old_file
        self.new_file = website.new_file
        self.old_content = website.old_content

    def create_reports(self):
        """Update site logs, print result, create snapshot, create diff, and prepare email."""
        log_content = "Change: {}. Change detected in the robots.txt file.".format(self.url)
        self.update_site_log(log_content)
        logs.update_main_log(log_content)
        print(log_content)
        self.create_snapshot()
        diff_file = self.create_diff_file()
        email_subject = "{} Robots.txt Change".format(self.name)
        link = "<a href=\"{}\">{}</a>".format(self.url + "robots.txt", self.url + "robots.txt")
        email_content = "A change has been detected in the {} robots.txt file. " \
                        "Copies of the old file and new file are attached. " \
                        "\n\nView the live robots.txt file: {}" \
                        "".format(self.url, link)

        email_body = emails.get_site_email_body(email_content)
        emails.site_emails.append((self.email, email_subject, email_body,
                                   self.old_file, self.new_file, diff_file))

    @logs.unexpected_exception_handling
    def create_diff_file(self):
        """Create and return the location of an HTML file containing a diff table."""
        old_list = self.old_content.split('\n')
        new_list = self.new_content.split('\n')
        diff_html = difflib.HtmlDiff().make_file(old_list, new_list, "Previous", "New")

        file_name = self.timestamp.replace(",", " T").replace(":", "-") + " Robots.txt Diff.html"
        diff_file = self.dir + "/snapshots/" + file_name
        if not os.path.isdir(self.dir + "/snapshots"):
            os.mkdir(self.dir + "/snapshots")

        with open(diff_file, 'x') as f:
            f.write(diff_html)

        return diff_file


class FirstRunReport(Report):
    """Log, print, and email the result (first run without error) of a single robots.txt check."""

    def create_reports(self):
        """Update site log, update main log, print result, create snapshot, and prepare email."""
        log_content = "First run: {}. First successful check of robots.txt file.".format(self.url)
        self.update_site_log(log_content)
        logs.update_main_log(log_content)
        print(log_content)
        self.create_snapshot()
        email_subject = "First {} Robots.txt Check Complete".format(self.name)
        email_content = "The first successful check of the {} robots.txt file is complete. " \
                        "Going forwards, you'll receive an email if the robots.txt file changes " \
                        "or if there's an error during the check. Otherwise, you can assume " \
                        "that the file has not changed.\n\nThe extracted content is shown below:" \
                        "\n\n-----START OF FILE-----\n\n{}\n\n-----END OF FILE-----\n\n" \
                        "".format(self.url, self.new_content)

        email_body = emails.get_site_email_body(email_content)
        emails.site_emails.append((self.email, email_subject, email_body))


class ErrorReport(Report):
    """Log, print, and email the result (error) of a single robots.txt check.

    Attributes:
        err_message (str): A description of the error logged during RobotsCheck.

    """

    def __init__(self, website, name, email):
        super().__init__(website, name, email)
        self.err_message = website.err_message

    def create_reports(self):
        """Update site log, update main log, print result, and prepare email."""
        log_content = "Error: {}. {}".format(self.url, self.err_message)
        # Only create/update site log if site directory exists
        if (os.path.isdir(self.dir)) and (self.dir[-5:] != "data/"):
            self.update_site_log(log_content)
        logs.update_main_log(log_content)
        print(log_content)
        email_subject = "{} Robots.txt Check Error".format(self.name)
        email_content = "There was an error while checking the {} robots.txt file. " \
                        "The check was not completed. The details are shown below.\n\n{}" \
                        "".format(self.url, self.err_message)

        email_content = emails.replace_angle_brackets(email_content)
        email_body = emails.get_site_email_body(email_content)
        emails.site_emails.append((self.email, email_subject, email_body))


def main():
    """Run all checks and handle fatal errors."""
    try:
        sites_data = sites_from_file(config.MONITORED_SITES)
        RunChecks(sites_data).check_all()

    except Exception as fatal_err:
        # Fatal error during CSV read or RunChecks
        fatal_err_msg = logs.get_err_str(fatal_err, "Fatal error.")
        logs.log_error(fatal_err_msg)

        email_subject = "Robots.txt Check Fatal Error"
        email_content = "There was a fatal error during the latest robots.txt checks which " \
                        "caused the program to terminate unexpectedly."

        email_body = emails.get_admin_email_body(email_content)
        emails.admin_email.append((config.ADMIN_EMAIL, email_subject, email_body))

    finally:
        if config.EMAILS_ENABLED:
            emails.send_emails(emails.admin_email)
        else:
            print("Note: the sending of emails is disabled in config.py.")

        logs.update_main_log("\n{}END OF RUN{}\n".format("-"*20, "-"*20), timestamp=False)


if __name__ == "__main__":
    main()
