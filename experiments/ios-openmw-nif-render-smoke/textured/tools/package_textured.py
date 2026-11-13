"""Reuse the complete G1B Mach-O/SDK/bundle/IPA gates for the isolated G1C app."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import resources
from support import package

package.APP_NAME = 'IOSOpenMWTexturedNif.app'
package.EXECUTABLE = 'IOSOpenMWTexturedNif'
package.BUNDLE_ID = 'org.openmw.experiments.ios-openmw-textured-nif'
package.PREFIX = 'Payload/' + package.APP_NAME + '/'
package.core.APP_NAME, package.core.PREFIX = package.APP_NAME, package.PREFIX

if __name__ == '__main__':
    package.main()
