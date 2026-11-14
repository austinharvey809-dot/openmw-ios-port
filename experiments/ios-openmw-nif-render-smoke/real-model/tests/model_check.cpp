#include "StaticModel.hpp"
#include "StaticProperties.hpp"
#include <iostream>
#include <osg/Geode>
#include <osg/Geometry>
#include <osg/ComputeBoundsVisitor>
#include <osg/Texture2D>
namespace {
void check(bool ok,const char* why){if(!ok)throw std::runtime_error(why);}
void properties(osg::Node* geode,const std::string& mode){
 auto& ss=*geode->getStateSet();
 const auto* depth=dynamic_cast<const osg::Depth*>(ss.getAttribute(osg::StateAttribute::DEPTH));
 const bool noTest=mode=="depth-off"||mode=="depth-write-only"||mode=="inheritance";
 const bool write=mode!="depth-off"&&mode!="depth-read-only";
 check(depth&&depth->getWriteMask()==write&&depth->getFunction()==(noTest?osg::Depth::ALWAYS:osg::Depth::LEQUAL),"Depth flags/child override mismatch");
 check(ss.getMode(GL_DEPTH_TEST)==(mode=="depth-off"?osg::StateAttribute::OFF:osg::StateAttribute::ON),"Depth-test enable mismatch");
 const bool twoSided=mode=="two-sided"||mode=="inheritance";
 check(ss.getMode(GL_CULL_FACE)==(twoSided?osg::StateAttribute::OFF:osg::StateAttribute::ON),"Inherited culling mismatch");
 auto* front=dynamic_cast<const osg::FrontFace*>(ss.getAttribute(osg::StateAttribute::FRONTFACE));
 check(front&&front->getMode()==(mode=="clockwise"||mode=="mirrored"?osg::FrontFace::CLOCKWISE:osg::FrontFace::COUNTER_CLOCKWISE),"Face winding/mirror mismatch");
 const bool blending=mode=="alpha-blend"||mode=="alpha-unsorted"||mode=="inheritance";
 check(ss.getMode(GL_BLEND)==(blending?osg::StateAttribute::ON:osg::StateAttribute::OFF),"Alpha blend inheritance/override mismatch");
 if(blending){auto* bf=dynamic_cast<const osg::BlendFunc*>(ss.getAttribute(osg::StateAttribute::BLENDFUNC));
 check(bf&&bf->getSource()==GL_SRC_ALPHA&&bf->getDestination()==GL_ONE_MINUS_SRC_ALPHA,"Blend factors mismatch");}
 check(ss.getRenderingHint()==(blending&&mode!="alpha-unsorted"?osg::StateSet::TRANSPARENT_BIN:osg::StateSet::DEFAULT_BIN),"Alpha sorter mismatch");
 int test=-1;float threshold=-1;
 check(ss.getUniform("alphaTestMode")&&ss.getUniform("alphaTestMode")->get(test)&&test==(mode=="alpha-test"?4:0),"GLES alpha test mode mismatch");
 check(ss.getUniform("alphaThreshold")&&ss.getUniform("alphaThreshold")->get(threshold),"Missing alpha threshold");
 if(mode=="alpha-test")check(std::abs(threshold-128.f/255.f)<1e-6f,"Alpha threshold mismatch");
 auto* geometry=dynamic_cast<osg::Geometry*>(geode->asGeode()->getDrawable(0));
 auto* colors=dynamic_cast<osg::Vec4Array*>(geometry->getColorArray());
 const osg::Vec4 expected=mode=="vertex-ignore"?osg::Vec4(.25,.5,.75,1):mode=="vertex-diffuse"?osg::Vec4(.2,.4,.6,.5):osg::Vec4(1,1,1,1);
 check(colors&&colors->size()==4&&(*colors)[0]==expected,"Material/vertex-color selection mismatch");
 auto* tex=dynamic_cast<const osg::Texture2D*>(ss.getTextureAttribute(0,osg::StateAttribute::TEXTURE));
 check(tex&&tex->getFilter(osg::Texture::MIN_FILTER)==(mode=="rug-properties"?osg::Texture::LINEAR_MIPMAP_LINEAR:osg::Texture::LINEAR),"Genuine filter mismatch");
 check(tex->getUseHardwareMipMapGeneration()==(mode=="rug-properties"),"Mip generation mismatch");
 check(tex->getWrap(osg::Texture::WRAP_S)==osg::Texture::REPEAT&&tex->getWrap(osg::Texture::WRAP_T)==osg::Texture::REPEAT,"Texture wrap mismatch");
 // Value-copy inheritance must not let a child's replacement mutate siblings.
 Nif::NiZBufferProperty parent,child;parent.mFlags=0;child.mFlags=3;
 parent.mController=Nif::NiTimeControllerPtr(nullptr);child.mController=Nif::NiTimeControllerPtr(nullptr);
 G1D::StaticProperties a;a.depth=&parent;auto b=a;G1D::inheritProperty(b,&child,"sibling-test");
 check(a.depth==&parent&&b.depth==&child,"Sibling property isolation mismatch");
 // Exercise all encoded alpha-test functions, not just the rug's opaque case.
 for(unsigned i=0;i<8;++i){Nif::NiAlphaProperty alpha;alpha.mFlags=0x200|(i<<10);alpha.mThreshold=128;
 alpha.mController=Nif::NiTimeControllerPtr(nullptr);
 G1D::StaticProperties effective;G1D::inheritProperty(effective,&alpha,"alpha-test-table");
 osg::ref_ptr<osg::StateSet> flags=new osg::StateSet;G1D::applyStaticState(*flags,effective,1);
 int actual=-1;check(flags->getUniform("alphaTestMode")->get(actual)&&actual==int(i),"Alpha test table mismatch");}
}
}
int main(int argc,char** argv){try{if(argc!=3&&argc!=4)throw std::runtime_error("Usage: model-check private-directory STAT-id [fixture]");
 auto model=G1D::load(argv[1],argv[2]);osg::ComputeBoundsVisitor visitor;model.scene->accept(visitor);auto bounds=visitor.getBoundingBox();
 if(!bounds.valid())throw std::runtime_error("Owned scene has invalid bounds after parser/VFS release");
 const std::string mode=argc==4?argv[3]:"private";
 if(argc==4&&(bounds.xMin()!=(mode=="mirrored"?0:1)||bounds.xMax()!=(mode=="mirrored"?1:2)||bounds.yMin()!=(mode=="mirrored"?1:2)||bounds.yMax()!=(mode=="mirrored"?2:3)||bounds.zMin()!=3||bounds.zMax()!=3))throw std::runtime_error("Hierarchy transform/ownership mismatch");
 if(argc==4){auto* root=model.scene->getChild(0)->asGroup();auto* child=root->getChild(0)->asGroup();auto* shape=child->getChild(0)->asGroup();auto* geode=shape->getChild(0);
 auto* tex=dynamic_cast<osg::Texture2D*>(geode->getStateSet()->getTextureAttribute(0,osg::StateAttribute::TEXTURE));
 if(!tex||!tex->getImage()||tex->getImage()->s()!=4||tex->getImage()->data()[0]!=255||tex->getImage()->data()[3]!=255)throw std::runtime_error("DDS decode/owned image mismatch");properties(geode,mode);}
 std::cout<<"{\"status\":\"PASS\",\"vertices\":"<<model.vertices<<",\"triangles\":"<<model.triangles<<",\"shapes\":"<<model.shapes<<"}\n";return 0;
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
