
# So far
we have already imported a zemax file into Optiland and then tried importing into Raycrafter. in this case the import into Optiland mostly worked with some issues. import into Raycrafter initially had more issues, but these were also mostly resolved. some remain. 

# Need now
We want an evaluation repo that will house our attempts to evaluate Optiland and Raycrafter WRT to Zemax. It will be based on the `evaluation` folder. it will have a designs folder. subfolders of that will be optical designs as ZMX exported by Zemax. In turn this will have subfolders:  `Zemax_reference_output` that contains output we want Optiland to match. There will be an `optiland_analysis` subfolder that contains our best attempt to have optiland match the Zemax. This is saved files: csv, json, png, etc from optiland. use descriptive filenames. A readme in that folder to explain what each is. 
Currently that does not exist. Some of it may be in the `evaluation` sub-folder within `evaluation` or may be in the Artifacts: You made two artifacts for the current design on there. these are still on my account. 

## New HTML summaries
I want equivalent content to the Artifacts in one webpage. Put in an HTML_summary sub-folder. This can pull images and data off the optiland folder. The Artifacts will end up polluting my Claude account as the project expands. I want to ultimately remove them from my account and have the ground truth live in thee repo.

## More designs
We will add more designs over time. Set up GH pages run off the project root such that users can browse the design html summaries. So the landing page explains what the project is, what the repo does, and lists the designs. Once we have a few designs up there we may find common elements and can come up with a traffic light system to indicate even on the summary page what works and does not work. 

## Link to raycrafter finally
I will now have a place I can point the raycrafter to the repo and get *it* to process designs that largely work in Optiland. The goal being to have them also work in Raycrafter. 

# Repo organisation
Set up the repo with the same cookie cutter and organisation as the raycrafter docs. However the webpage style should match the artifacts. Not the raycrafter docs site. 

Look at the CLAUD.md files in the existing repos we have set up. We should copy relevant stuff into a CLAUDE.md we make for the evaluation repo
