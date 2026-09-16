from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait


options = Options()
options.debugger_address = "localhost:9222"
driver = webdriver.Chrome(options=options)
driver.implicitly_wait(1)
url_start = driver.current_url
driver.get(url_start)

# Required actions.
# Hit plus button
# <span class="ps-button-wrapper" title="Add a New Value"><a id="PTS_ADDMODE_BTN" class="ps-button" role="button" aria-pressed="false" onclick="javascript:cancelBubble(event);" href="javascript:submitAction_win0(document.win0,'PTS_ADDMODE_BTN');"><img src="/cs/sa92dev/cache/cache082826a/PT_ROW_ADD_32_302.SVG" id="PTS_ADDMODE_BTN$IMG" class="ps-img" alt=""><span class="ps-text">Add</span></a></span>

# Input role name and force the sign on PC to run UHS_CS_DEVINQ
# <input type="text" id="PTS_FILTER_NOOP_PTS_PROMPT2$0" class="ps-edit" sfn="ROLENAME" maxlength="30" pt_fn="ROLENAME" pt_flbl="Role Name" onfocus="javascript:onSmartPromptDataChange(event, this, '', 'onfocus', 'submitAction_win0');" onfocusout="javascript:onSmartPromptDataChange(event, this, '', 'onfocusout');" rn="PTS_FILTER_NOOP" fn="PTS_PROMPT2" pt="PSROLEDEFN" value="" listhdr0="Role Name" listhdr1="Role Type" listhdr2="Role-Query Name" onclick="javascript:cancelBubble(event);" onchange="addchg_win0(this);oChange_win0=this;/*8400,0*/" psnchg="0" validatedflag="true">

# Push the add button 
# <div class="ps_box-button psc_primary pts_padding-top025em" id="win0srchdivPTS_SRCH_BTN"><span id="PTS_SRCH_BTN$span" class="ps-button-wrapper"><a id="PTS_SRCH_BTN" class="ps-button" accesskey="1" onclick="javascript:cancelBubble(event);" href="javascript:submitAction_win0(document.win0,'PTS_SRCH_BTN');" role="button" title="Add" aria-label="Add" ptlinktgt="pt_peoplecode">Add</a></span><!-- PTS_SRCH_BTN --></div>



# Will get transfered to another page where we will add several hundress rows.
# Row: Record Name, Field Name, Access Code. Access Code should be set to Authorized
# ACAD_SUBPL_WHIF, EMPLID, Authorized

# Add record name ADM_T189_PER_EC
# <input type="text" id="RECNAME$0" class="ps-edit" pt_fn="RECNAME" pt_flbl="Record (Table) Name" onfocus="javascript:onSmartPromptDataChange(event, this, '', 'onfocus', 'submitAction_win0');" onfocusout="javascript:onSmartPromptDataChange(event, this, '', 'onfocusout');" rn="EODP_ROLRECFLD" fn="RECNAME" deferred="1" pt="EODP_RECORDLIST" value="" listhdr0="Record (Table) Name" listhdr1="Record Description" maxlength="15" onclick="javascript:cancelBubble(event);" aria-required="true" validatedflag="true">

# Add field name SSN
# <input type="text" id="EODP_ROLRECFLD_FIELDNAME$0" class="ps-edit" pt_fn="FIELDNAME" pt_flbl="Field Name" onfocus="javascript:onSmartPromptDataChange(event, this, '', 'onfocus', 'submitAction_win0');" onfocusout="javascript:onSmartPromptDataChange(event, this, '', 'onfocusout');" rn="EODP_ROLRECFLD" fn="FIELDNAME" deferred="1" dependson0="RECNAME" pt="EODP_FIELDSLIST" value="" skipfn0="RECNAME" listhdr0="Field Name" maxlength="18" onclick="javascript:cancelBubble(event);" aria-required="true">

# Set access code to Authorized
# <select id="EODP_ROLRECFLD_EODP_ACCESS_CD$0" class="ps-dropdown" size="1" onclick="javascript:cancelBubble(event);" fn="EODP_ACCESS_CD" onchange="if (typeof onSmartSelectDataChange === 'function') { onSmartSelectDataChange(this); }" aria-required="true">
# <option value="" selected="selected" aria-invalid="true"> 
# </option><option value="Y">Authorized</option>
# <option value="N">Not Authorized</option>
# </select>

# Hit the plus button to insert another row.
# <span class="ps-button-wrapper" title="Insert Row"><a id="EODP_RRF_WRK_EODP_INSERT_ROW" class="ps-button" role="button" onclick="javascript:cancelBubble(event);" href="javascript:submitAction_win0(document.win0,'EODP_RRF_WRK_EODP_INSERT_ROW');"><img src="/cs/sa92dev/cache/cache082826a/PT_ROW_ADD_32_302.SVG" id="EODP_RRF_WRK_EODP_INSERT_ROW$IMG" class="ps-img" alt="Insert Row"></a></span>

# Add another row with the values ACAD_PLAN EMPLID 

# Hit the save button
# <div class="ps_box-button psc_primary " id="win0divEODP_RRF_WRK_SAVE_PB"><span id="EODP_RRF_WRK_SAVE_PB$span" class="ps-button-wrapper"><a id="EODP_RRF_WRK_SAVE_PB" class="ps-button" role="button" ptlinktgt="pt_peoplecode" onclick="javascript:cancelBubble(event);" href="javascript:submitAction_win0(document.win0,'EODP_RRF_WRK_SAVE_PB');" aria-label="Save" accesskey="S"><abbr class="PTUNDERLINE">S</abbr>ave</a></span><!-- EODP_RRF_WRK_SAVE_PB --></div>


# After hitting save there is an element that displays. Below is me manually setting it to show.
# <div class="psc_processing psc_hidden" id="WAIT_win0" style="visibility: visible; display: block; right: 0px;"><img id="processing" src="/cs/sa92dev/cache/cache082826a/PT_PROCESSING_FMODE_1.gif" alt="Processing... please wait" title="Processing... please wait"></div>

# However when the load is complete it reverts to this state.
# <div class="psc_processing psc_hidden" id="WAIT_win0" style="visibility: hidden; display: none; right: 0px;"><img id="processing" src="/cs/sa92dev/cache/cache082826a/PT_PROCESSING_FMODE_1.gif" alt="Processing... please wait" title="Processing... please wait"></div>

# When the load is complete this indiviual addittion is complete.

# Input CSVs will contain "ROLENAME","RECNAME","FIELDNAME"
# Should process one rolename and recname and fieldnames assosciated with it.



