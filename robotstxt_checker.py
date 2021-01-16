""" Monitor and report changes across multiple website robots.txt files."""
# TODO: Complete core functionality
# TODO: Create function to construct standard error strings
# TODO: Write tests and fix bugs

import csv
import datetime
import difflib
import os
import requests
import smtplib
import time
import traceback
import yagmail

# Site check data file location (see sites_from_file() documentation for details)
MONITORED_SITES = "monitored_sites.csv"

# File location of main log which details check and change history
MAIN_LOG = "data/main_log.txt"

# Email address of the program administrator, included as a point of contact in all emails
# This address will receive a summary report every time checks are run
ADMIN_EMAIL = "robotstxtmonitor@gmail.com"

# A Gmail address which will send emails
# Less secure app access must be enabled: https://support.google.com/accounts/answer/6010255
SENDER_EMAIL = "robotstxtmonitor@gmail.com"

# Toggle ('True' or 'False') whether emails are enabled (to both site owners and program admin)
EMAILS_ENABLED = True

# A list of tuples in the form (address, subject, body, *attachments); refer to send_emails()
emails = []
admin_email = []

# Errors which should be investigated
unexpected_errors = []


def sites_from_file(file):
    """Extract monitored sites data from a CSV and return as a list of lists.

    Args:
        file (str): file location of a CSV file with the following attributes.
            - Header row labelling the three columns, as listed below.
            - url (col1): the absolute URL of the website homepage, with a trailing slash.
            - name (col2): the website's name identifier (letters/numbers only).
            - email (col3): the email address of the owner, who will receive alerts.

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
                    err_msg = "Error, couldn't extract row {} from CSV. TYPE: {}, DETAILS: {}, " \
                              "TRACEBACK:\n\n{}\n".format(row_num, type(e), e, get_trace_str(e))

                    print(err_msg)
                    unexpected_errors.append(err_msg)
                    update_main_log(err_msg)

            row_num += 1

    return data


def get_timestamp(str_format="%d-%m-%y, %H:%M"):
    """Return the current time as a string (default: 'day-month-year, hour:minute').

    Args:
        str_format (str): a valid datetime.datetime.strftime format.

    """
    current_time = datetime.datetime.now()
    return current_time.strftime(str_format)


def get_trace_str(exception):
    """Return a str representation of an Exception traceback."""
    return "".join(traceback.format_tb(exception.__traceback__)).strip()


def update_main_log(message):
    """Update the main log with a single message (str)."""
    try:
        with open(MAIN_LOG, 'a') as f:
            f.write("{}: {}\n".format(get_timestamp(), message))

    # Catch all to prevent fatal error; log error to be investigated instead
    except Exception as e:
        err_msg = "Error when updating the main log. TYPE: {}, DETAILS: {}, TRACEBACK:\n\n" \
                  "{}\n".format(type(e), e, get_trace_str(e))

        print(err_msg)
        unexpected_errors.append(err_msg)


def get_user_email_body(main_content):
    """Return the full email body content, including generic and unique content.

    Args:
        main_content (str): the unique email content to be inserted into the template.

    """
    # Avoid error strings being interpreted as HTML
    main_content = main_content.replace("<", "{").replace(">", "}")

    return "Hi there,\n\n{}\n\nThis is an automated message; please do not reply directly " \
           "to this email. If you have any questions, bug reports, or feedback, please " \
           "contact the tool administrator: {}. Thanks!".format(main_content, ADMIN_EMAIL)


def get_admin_email_body(main_content):
    """Return the full email body content, including generic and unique content.

    Args:
        main_content (str): the unique email content to be inserted into the template.

    """
    if len(unexpected_errors) == 0:
        return "Hi there,\n\n{}\n\nThere were no unexpected errors.".format(main_content)

    else:
        # Avoid error strings being interpreted as HTML
        email_errs = [e.replace("<", "{").replace(">", "}") for e in unexpected_errors.copy()]

        return "Hi there,\n\n{}\n\nUnexpected errors are listed below:\n\n" \
               "{}".format(main_content, "\n\n".join(email_errs))


def set_email_login():
    pw = input("Type in {} password and press Enter: ".format(SENDER_EMAIL))
    yagmail.register(SENDER_EMAIL, pw)


def save_unsent_email(address, subject, body):
    """Save the key details of an email which could not be sent.

    Args:
        - address (str): the destination email address
        - subject (str): the subject line of the email
        - body (str): the main body content of the email

    """
    try:
        if not os.path.isdir('data/_unsent_emails'):
            os.mkdir('data/_unsent_emails')

        file_name = get_timestamp(str_format="%d-%m-%y T %H-%M-%S") + ".txt"
        with open('data/_unsent_emails/' + file_name, 'x') as f:
            f.write(address + "\n\n" + subject + "\n\n" + body)

        print("Unsent email content successfully saved in /data/_unsent_emails/.")
        time.sleep(1)

    except Exception as e:
        err_msg = "Error saving unsent email. TYPE: {}, DETAILS: {}, TRACEBACK:\n\n" \
                  "{}\n".format(type(e), e, get_trace_str(e))

        print(err_msg)
        unexpected_errors.append(err_msg)
        update_main_log(err_msg)


def send_emails(emails_list):
    """Send emails based on a list of tuples in the form (address, subject, body, *attachments).

    Args:
        emails_list (list): A list of tuples, with each tuple containing the following data:
            - address (str): the destination email address
            - subject (str): the subject line of the email
            - body (str): the main body content of the email
            - *attachments (str, optional): 0 or more attachment file locations

    """
    # TODO: complete and document function to send email
    # TODO: pass and include attachments for applicable emails
    if not EMAILS_ENABLED:
        return None

    try:
        with yagmail.SMTP(SENDER_EMAIL) as server:
            print("Sending {} email(s)...".format(len(emails_list)))
            valid_login = True
            for address, subject, body, *attachments in emails_list:
                # Allow for send re-attempt if original login failed and password updated
                while valid_login:
                    try:
                        server.send(address, subject, body)
                        print("Email sent to {} (subject: {}).".format(address, subject))
                        time.sleep(0.5)
                        # Break out of while loop to move to next email
                        break

                    except smtplib.SMTPAuthenticationError as e:
                        short_err_msg = "Email login failed. Please ensure that less secure app " \
                                        "access is 'On' for the sender email Google account and " \
                                        "that your saved login details are correct."

                        print(short_err_msg)
                        answer = input("Type 'y' and press Enter to update your saved password "
                                       "and re-attempt the login: ")

                        if answer.lower().strip() == 'y':
                            set_email_login()

                        else:
                            err_msg = short_err_msg + "These can be updated using " \
                                      "set_email_login().\n\n" \
                                      "TYPE: {}. DETAILS:\n\n{}\n\n".format(type(e), e)

                            print(err_msg)
                            update_main_log(err_msg)
                            # Skip send attempts for any subsequent emails
                            valid_login = False

                    # Catch all to prevent all emails failing; log error to be investigated instead
                    except Exception as e:
                        err_msg = "Error sending email to {}. TYPE: {}. DETAILS:\n\n{}\n\n" \
                              "TRACEBACK:\n\n{}\n".format(address, type(e), e, get_trace_str(e))

                        print(err_msg)
                        unexpected_errors.append(err_msg)
                        update_main_log(err_msg)
                        save_unsent_email(address, subject, body)
                        # Break out of while loop to move to next email
                        break

    # Catch all to prevent fatal error; log error to be investigated instead
    except Exception as e:
        err_msg = "Error using email server. TYPE: {}. DETAILS:\n\n{}\n\nTRACEBACK:\n\n" \
                  "{}\n".format(type(e), e, get_trace_str(e))

        print(err_msg)
        unexpected_errors.append(err_msg)
        update_main_log(err_msg)


class RunChecks:
    """Run robots.txt checks across monitored websites.

    This class is used to run robots.txt checks by initialising RobotsCheck instances,
    before initialising the relevant Report subclass to generate logs and communications.

    Attributes:
        sites (list): a list of lists, with each list item representing a single site's
        attributes in the form [url, name, email]. Each attribute is detailed below.
            - url (str): the absolute URL of the website homepage, with a trailing slash.
            - name (str): the website's name identifier (letters/numbers only).
            - email (str): the email address of the owner, who will receive alerts.

        no_change (int): a count of site checks with no robots.txt change.
        change (int): a count of site checks with a robots.txt change.
        first_run (int): a count of site checks which were the first successful check.
        error (int): a count of site checks which could not be completed due to an error.

    """

    def __init__(self, sites):
        self.sites = sites.copy()
        self.no_change, self.change, self.first_run, self.error = 0, 0, 0, 0

        # If /data doesn't exist yet, create directory and main log file
        if not os.path.isdir('data'):
            os.mkdir('data')
            f = open(MAIN_LOG, 'x')
            f.close()

    def check_all(self):
        """Run robots.txt checks and reports for all sites."""
        start_content = "Starting checks on {} sites.".format(len(self.sites))
        update_main_log(start_content)
        print(start_content)

        self.reset_counts()
        for site_attributes in self.sites:
            self.check_site(site_attributes)

        summary = "Checks and reports complete. No change: {}. Change: {}. First run: {}. " \
                  "Error: {}.".format(self.no_change, self.change, self.first_run, self.error)

        print(summary)
        update_main_log(summary + "\n\n{}\n".format("-" * 150))
        send_emails(emails)

        email_subject = "Robots.txt Checks Complete"
        email_body = get_admin_email_body(summary)
        admin_email.append((ADMIN_EMAIL, email_subject, email_body, MAIN_LOG))

    def check_site(self, site_attributes):
        """Run a robots.txt check and report for a single site.

        Attributes:
            site_attributes (list): a list representing a single site's attributes
            in the form [url, name, email]. Each attribute is detailed below.
                - url (str): the absolute URL of the website homepage, with a trailing slash.
                - name (str): the website's name identifier (letters/numbers only).
                - email (str): the email address of the owner, who will receive alerts.

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

        except Exception as e:
            err_msg = "Unexpected error for site: {}. TYPE: {}, DETAILS: {}, " \
                      "TRACEBACK:\n\n{}\n".format(site_attributes, type(e), e, get_trace_str(e))

            print(err_msg)
            unexpected_errors.append(err_msg)
            update_main_log(err_msg)
            email_subject = "Robots.txt Check Error"
            email_content = "There was an unexpected error while checking or reporting on the " \
                            "robots.txt file of a site which is associated with your email. " \
                            "If this is the first check, please ensure all site details " \
                            "were provided in the correct format. The error details are " \
                            "shown below.\n\n{}".format(err_msg)

            email_body = get_user_email_body(email_content)
            emails.append((site_attributes[2].strip(), email_subject, email_body))
            self.error += 1

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
        old_content (str): the previous check robots.txt content.
        new_content (str): the latest check robots.txt content.

    """

    def __init__(self, url):
        self.url = url
        self.first_run = False
        self.err_message = None
        self.file_change = False
        if self.url[4] == 's':
            self.dir = "data/" + self.url[8:-1]
        else:
            self.dir = "data/" + self.url[7:-1]
        self.old_file = self.dir + "/old_file.txt"
        self.new_file = self.dir + "/new_file.txt"
        self.old_content = None
        self.new_content = None

        if (self.url[:4] != "http") or (self.url[-1] != "/"):
            self.err_message = "{} is not a valid site URL. The site URL must be absolute and " \
                               "end in a slash, e.g. 'https://www.example.com/'.".format(url)

        # If URL is valid and site directory doesn't exist, create directory
        elif not os.path.isdir(self.dir):
            try:
                os.mkdir(self.dir)
            except Exception as e:
                self.err_message = "Error when creating {} directory. TYPE: {}, DETAILS: {}, " \
                                   "TRACEBACK:\n\n{}" \
                                   "\n".format(self.url, type(e), e, get_trace_str(e))

                unexpected_errors.append(self.err_message)

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
            # Anticipated errors caught in download_robotstxt() and logged in self.err_message
            if not self.err_message:
                self.err_message = "Unexpected error during {} check. TYPE: {}, DETAILS: {}, " \
                                   "TRACEBACK:\n\n{}" \
                                   "\n".format(self.url, type(e), e, get_trace_str(e))

                unexpected_errors.append(self.err_message)

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
                req = requests.get(robots_url, allow_redirects=False, timeout=40)

            except requests.exceptions.Timeout as e:
                err = "{} timed out before sending a valid response.".format(robots_url)
                if attempt < (max_attempts - 1):
                    print(err + attempts_str)
                    time.sleep(wait)
                else:
                    # Final connection attempt failed
                    self.err_message = err + " TYPE: {}\n\nDETAILS: {}".format(type(e), e)
                    raise

            except requests.exceptions.ConnectionError as e:
                err = "There was a connection error when accessing {}.".format(robots_url)
                if attempt < (max_attempts - 1):
                    print(err + attempts_str)
                    time.sleep(wait)
                else:
                    # Final connection attempt failed
                    self.err_message = err + " TYPE: {}\n\nDETAILS: {}".format(type(e), e)
                    unexpected_errors.append(self.err_message)
                    raise

            else:
                # If no exceptions raised
                if req.status_code != 200:
                    self.err_message = "{} returned a {} status code." \
                                       "".format(robots_url, req.status_code)
                    raise requests.exceptions.HTTPError

                return req.text

    def update_records(self, new_extraction):
        """Update the files containing the current and previous robots.txt content.

        If the robots.txt file has been successfully checked previously,
        overwrite old_file with the contents of new_file (from the previous check).
        Otherwise, create the content files and set first_run = True.
        Then, add the new robots.txt extraction content to new_file.

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
        self.new_content = new_extraction
        with open(self.new_file, 'w') as new:
            new.write(self.new_content)

    def check_diff(self):
        """Check for file differences and update self.file_change."""
        if self.old_content != self.new_content:
            self.file_change = True


class Report:
    """Report/log the results of a single robots.txt check.

    This is a base class; more specific child classes should be instantiated.

    Attributes:
        url (str): the absolute URL of the website homepage, with a trailing slash.
        dir (str): the name of the directory containing website data.
        new_content (str): the latest check robots.txt content.
        name (str): the website's name identifier.
        email (str): the email address of the owner, who will receive alerts.
        timestamp (str): the (approximate) time of the check.

    """

    def __init__(self, website, name, email):
        self.url = website.url
        self.dir = website.dir
        self.new_content = website.new_content
        self.name = name
        self.email = email
        self.timestamp = get_timestamp()

    def update_site_log(self, message):
        """Update the site log with a single message (str)."""
        try:
            log_file = self.dir + "/log.txt"
            # Append or create file if it doesn't exist
            with open(log_file, 'a+') as f:
                f.write("{}: {}\n".format(self.timestamp, message))

        except Exception as e:
            err_msg = "Error when updating the site log. TYPE: {}, DETAILS: {}, TRACEBACK:\n\n" \
                      "{}\n".format(type(e), e, get_trace_str(e))

            print(err_msg)
            unexpected_errors.append(err_msg)
            update_main_log(err_msg)

    def create_snapshot(self):
        """Create and return the location of a text file containing the latest content."""
        file_name = self.timestamp.replace(",", " T").replace(":", "-") + " Snapshot.txt"
        snapshot_file = self.dir + "/snapshots/" + file_name
        if not os.path.isdir(self.dir + "/snapshots"):
            os.mkdir(self.dir + "/snapshots")

        with open(snapshot_file, 'x') as f:
            f.write(self.new_content)

        return snapshot_file


class NoChangeReport(Report):
    """Log and print the result (no change) of a single robots.txt check."""

    def create_reports(self):
        """Update the site log and print result."""
        log_content = "No change: {}. No changes to robots.txt file.".format(self.url)
        self.update_site_log(log_content)
        print(log_content)


class ChangeReport(Report):
    """Log, print, and email the result (robots.txt change) of a single robots.txt check.

    Attributes:
        old_file (str): the file location of the previous check robots.txt content.
        old_content (str): the previous check robots.txt content.

    """

    def __init__(self, website, name, email):
        super().__init__(website, name, email)
        self.old_file = website.old_file
        self.old_content = website.old_content

    def create_reports(self):
        """Update site log, update main log, print result, create snapshot, and prepare email."""
        log_content = "Change: {}. Change detected in the robots.txt file.".format(self.url)
        self.update_site_log(log_content)
        update_main_log(log_content)
        print(log_content)
        self.create_snapshot()
        diff_file = self.create_diff_file()
        email_subject = "{} Robots.txt Change".format(self.name)
        email_content = "A change has been detected in the {} robots.txt file. " \
                        "The latest and previously recorded file contents are shown below." \
                        "\n\n-----START OF NEW FILE-----\n\n{}\n\n-----END OF NEW FILE-----" \
                        "\n\n-----START OF OLD FILE-----\n\n{}\n\n-----END OF OLD FILE-----" \
                        "".format(self.url, self.new_content, self.old_content)

        email_body = get_user_email_body(email_content)
        emails.append((self.email, email_subject, email_body, diff_file, self.old_file))

    def create_diff_file(self):
        """Create and return the location of an HTML file containing a diff table."""
        old_list = self.old_content.split('\n')
        new_list = self.new_content.split('\n')
        diff_html = difflib.HtmlDiff().make_file(old_list, new_list, "Previous", "New")

        file_name = self.timestamp.replace(",", " T").replace(":", "-") + " Diff.html"
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
        update_main_log(log_content)
        print(log_content)
        self.create_snapshot()
        email_subject = "First {} Robots.txt Check Complete".format(self.name)
        email_content = "The first successful check of the {} robots.txt file is complete. " \
                        "The extracted file content is shown below." \
                        "\n\n-----START OF FILE-----\n\n{}\n\n-----END OF FILE-----\n\n" \
                        "Going forwards, you'll receive an email if the robots.txt file changes " \
                        "or if there's an error during the check. Otherwise, you can assume " \
                        "that the file has not changed.".format(self.url, self.new_content)

        email_body = get_user_email_body(email_content)
        emails.append((self.email, email_subject, email_body))


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
        if os.path.isdir(self.dir):
            self.update_site_log(log_content)
        update_main_log(log_content)
        print(log_content)
        email_subject = "{} Robots.txt Check Error".format(self.name)
        email_content = "There was an error while checking the {} robots.txt file. " \
                        "The check was not completed. The details are shown below.\n\n{}" \
                        "".format(self.url, self.err_message)
        email_body = get_user_email_body(email_content)
        emails.append((self.email, email_subject, email_body))


def main():
    """Run all checks and handle fatal errors."""
    try:
        sites_data = sites_from_file(MONITORED_SITES)
        RunChecks(sites_data).check_all()

    except Exception as fatal_err:
        # Fatal error during CSV read or RunChecks
        fatal_err_msg = "Fatal error. TYPE: {}, DETAILS: {}, TRACEBACK:\n\n" \
                        "{}\n".format(type(fatal_err), fatal_err, get_trace_str(fatal_err))

        print(fatal_err_msg)
        unexpected_errors.append(fatal_err_msg)
        update_main_log(fatal_err_msg)
        email_subject = "Robots.txt Check Fatal Error"
        email_content = "There was a fatal error during the latest robots.txt checks which " \
                        "caused the program to terminate unexpectedly."
        email_body = get_admin_email_body(email_content)
        admin_email.append((ADMIN_EMAIL, email_subject, email_body))

    finally:
        if EMAILS_ENABLED:
            send_emails(admin_email)
        else:
            print("Note: emails are disabled. Details of the program run have been printed "
                  "and/or logged. Set 'EMAILS_ENABLED' to equal 'True' to send/receive emails.")


if __name__ == "__main__":
    # Use set_email_login() to save login details on first run or if email/password changes:
    # set_email_login()
    main()
